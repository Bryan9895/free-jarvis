import unittest
from jarvis.robot_transport import RobotPacket, SimulatedRobot


class RobotContractTests(unittest.TestCase):
    def test_safe_simulator(self):
        robot = SimulatedRobot()
        self.assertEqual(RobotPacket.decode(RobotPacket("ping").encode()).action, "ping")
        robot.request(RobotPacket("led", 1))
        self.assertTrue(robot.led_on)
        robot.request(RobotPacket("led", 0))
        self.assertFalse(robot.led_on)

    def test_rejects_unsafe_commands_and_bad_frames(self):
        for packet in (RobotPacket("motor_move", 100), RobotPacket("led", 100),
                       RobotPacket("sensor_read", "../secret"), RobotPacket("ping", "x")):
            with self.assertRaises(ValueError):
                packet.encode()
        for raw in (b"{}", b"hello\n", b'{"v":1,"action":"motor_move","value":3}\n',
                    b'{"v":1,"action":[],"value":null}\n'):
            with self.assertRaises(ValueError):
                RobotPacket.decode(raw)
