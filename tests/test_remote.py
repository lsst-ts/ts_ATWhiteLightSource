import asyncio
import unittest
import time

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.salobj import test_utils
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC


class WhiteLightSourceRemoteTests(unittest.TestCase):
    def setUp(self):
        self.csc = WhiteLightSourceCSC(sim_mode = 1)
        self.csc.summary_state = salobj.State.ENABLED

        # set short cooldown and warmup periods so the tests don't take hours
        self.csc.model.cooldownPeriod = 3
        self.csc.model.warmupPeriod = 3
        self.remote = salobj.Remote(SALPY_ATWhiteLight, index=None)

    def testPowerOnOff(self):
        """
        Tests we can power on through the Remote system.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            timeout = 5

            powerOn_topic = self.remote.cmd_powerLightOn.DataType()
            powerOn_topic.power = True
            ontask = asyncio.ensure_future(self.remote.cmd_powerLightOn.start(powerOn_topic, timeout))
            onresult = await ontask
            assert onresult.ack.result == "Done"
            powerOff_topic = self.remote.cmd_powerLightOff.DataType()
            powerOff_topic.power = False
            time.sleep(3)
            offtask = asyncio.ensure_future(self.remote.cmd_powerLightOff.start(powerOff_topic, timeout))
            offoutput = await offtask
            assert offoutput.ack.result == "Done"
        asyncio.get_event_loop().run_until_complete(doit())

    def testCantPowerOffDuringWarmup(self):
        """
        Tests we can power on through the Remote system, but receive
        an error when we try to immediately power off.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            timeout = 5

            powerOn_topic = self.remote.cmd_powerLightOn.DataType()
            powerOn_topic.power = True
            ontask = asyncio.ensure_future(self.remote.cmd_powerLightOn.start(powerOn_topic, timeout))
            onresult = await ontask
            assert onresult.ack.result == "Done"
            powerOff_topic = self.remote.cmd_powerLightOff.DataType()
            powerOff_topic.power = False
            with test_utils.assertRaisesAckError(ack=-302):
                offtask = asyncio.ensure_future(self.remote.cmd_powerLightOff.start(powerOff_topic, timeout))
                await offtask
        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
