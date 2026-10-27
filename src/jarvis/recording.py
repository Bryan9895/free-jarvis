"""PCM contínuo em segmentos temporários; só um endpoint completo vira intenção."""
import tempfile


class PCMRecording:
    def __init__(self, rate=16000, trace=None):
        # Até 20 s na RAM; depois arquivo temporário sem nome persistente.
        self.stream = tempfile.SpooledTemporaryFile(max_size=rate * 2 * 20)
        self.rate, self.trace = rate, trace
        self.samples = 0
        self.complete = False

    def append(self, chunk):
        data = chunk if isinstance(chunk, bytes) else chunk.tobytes()
        if len(data) % 2:
            raise ValueError('PCM16 desalinhado')
        self.stream.seek(0, 2)
        self.stream.write(data)
        self.samples += len(data) // 2

    def __len__(self):
        return self.samples

    def write_to(self, wav):
        if not self.complete:
            raise ValueError('Pedido incompleto não pode ser transcrito ou executado')
        self.stream.seek(0)
        for data in iter(lambda: self.stream.read(65536), b''):
            wav.writeframesraw(data)

    def max(self):
        from array import array
        self.stream.seek(0)
        result = -32768
        for data in iter(lambda: self.stream.read(65536), b''):
            values = array('h')
            values.frombytes(data)
            result = max(result, max(values))
        return result

    def close(self):
        self.stream.close()

    def __del__(self):
        self.close()
