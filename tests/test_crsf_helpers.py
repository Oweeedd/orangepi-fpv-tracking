import sys
import types
import unittest

for name in ("cv2", "serial", "yaml"):
    sys.modules.setdefault(name, types.ModuleType(name))

from tracking_crsf_lab import (
    CRSF_RAW_MAX,
    CRSF_RAW_MID,
    CRSF_RAW_MIN,
    pack_channels,
    raw_to_us,
    unpack_channels,
    us_to_raw,
)


class TestCRSFHelpers(unittest.TestCase):
    def test_channel_pack_roundtrip(self):
        channels = [172, 992, 1811, 500, 1200, 700, 1500, 1000,
                    800, 900, 1000, 1100, 1300, 1400, 1600, 1800]
        self.assertEqual(unpack_channels(pack_channels(channels)), channels)

    def test_us_mapping_endpoints(self):
        self.assertEqual(raw_to_us(CRSF_RAW_MIN), 988)
        self.assertEqual(raw_to_us(CRSF_RAW_MAX), 2012)
        self.assertLessEqual(abs(us_to_raw(1500) - CRSF_RAW_MID), 2)


if __name__ == "__main__":
    unittest.main()
