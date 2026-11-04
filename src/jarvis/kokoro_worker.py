"""Resident CPU TTS worker. Local paths only; no audio capture or playback."""
import contextlib
import importlib.metadata
import json
from pathlib import Path
import sys
import wave


def deny_network(event, _args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('Rede desabilitada durante a síntese Kokoro')


def verified_runtime():
    import torch
    expected = {'kokoro': '0.9.4', 'misaki': '0.9.4', 'transformers': '4.51.3'}
    if (not (3, 10) <= sys.version_info[:2] < (3, 13)
            or any(importlib.metadata.version(name) != version for name, version in expected.items())
            or torch.__version__ != '2.8.0+cpu' or torch.version.cuda is not None):
        raise ValueError('Use Python 3.10–3.12, Kokoro/Misaki 0.9.4, Transformers 4.51.3 e Torch 2.8.0+cpu')
    return {'kokoro_version': '0.9.4', 'torch_version': torch.__version__,
            'python_version': list(sys.version_info[:3]), 'language': 'pt-br', 'espeak': 'OK'}


def phoneme_units(text, g2p):
    phonemes, _ = g2p(text)
    if len(phonemes) <= 500:
        if phonemes:
            yield phonemes
        return
    if len(text) < 2:
        raise ValueError('Não foi possível segmentar o texto para Kokoro sem corte')
    middle = len(text) // 2
    split = text.rfind(' ', 0, middle + 1)
    split = split if split > 0 else middle
    yield from phoneme_units(text[:split], g2p)
    yield from phoneme_units(text[split:], g2p)


class KokoroVoice:
    def __init__(self, directory):
        # The script's sibling package is trusted application code, not PYTHONPATH.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from jarvis.kokoro_assets import verify_assets
        verified_runtime()
        verify_assets(directory)
        import torch
        from kokoro import KModel, KPipeline
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        self.torch = torch
        self.directory = Path(directory)
        model = KModel(repo_id='hexgrad/Kokoro-82M', config=str(self.directory / 'config.json'),
                       model=str(self.directory / 'kokoro-v1_0.pth')).to('cpu').eval()
        self.pipeline = KPipeline(lang_code='p', repo_id='hexgrad/Kokoro-82M', model=model, device='cpu')
        # Path, not a voice ID: KPipeline must never download a voice implicitly.
        self.voice = str(self.directory / 'pf_dora.pt')
        self.pipeline.load_voice(self.voice)

    def synthesize(self, text, filename):
        import numpy as np
        samples = 0
        with wave.open(filename, 'wb') as output, self.torch.inference_mode():
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            # generate_from_tokens rejects oversize phonemes. The default __call__
            # truncates them in this package version; never use that path here.
            for phonemes in phoneme_units(text, self.pipeline.g2p):
                for result in self.pipeline.generate_from_tokens(phonemes, voice=self.voice, speed=1):
                    audio = result.audio
                    if audio is None:
                        raise ValueError('Kokoro não gerou áudio para uma parte da resposta')
                    array = np.asarray(audio.detach().cpu().numpy(), dtype=np.float32).reshape(-1)
                    if not np.isfinite(array).all():
                        raise ValueError('Kokoro retornou amostras de áudio inválidas')
                    samples += len(array)
                    if samples > 24000 * 120:
                        raise ValueError('Síntese excedeu o limite por trecho; resposta visual preservada')
                    output.writeframes((np.clip(array, -1, 1) * 32767).astype('<i2').tobytes())
        if samples == 0:
            raise ValueError('Kokoro não produziu fala')


def main():
    sys.addaudithook(deny_network)
    voice = None
    lines = ['{"operation":"inspect"}'] if sys.argv[1:] == ['--inspect'] else sys.stdin
    for line in lines:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if request.get('operation') == 'inspect':
                    from kokoro import KModel, KPipeline
                    from misaki.espeak import EspeakG2P
                    import torch
                    info = verified_runtime()
                    EspeakG2P(language='pt-br')
                    print(json.dumps({'ok': True, 'runtime': info}), file=sys.__stdout__, flush=True)
                    return
                if voice is None:
                    voice = KokoroVoice(request['directory'])
                elif str(voice.directory) != request['directory']:
                    raise ValueError('Troca de modelo exige reinício do worker de voz')
                voice.synthesize(request['text'], request['filename'])
            print(json.dumps({'ok': True}), flush=True)
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            print(json.dumps({'error': message}), flush=True)
            return


if __name__ == '__main__':
    main()
