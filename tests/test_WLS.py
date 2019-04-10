import asyncio
import unittest

import SALPY_ATWhiteLight
from lsst.ts import salobj
from lsst.ts.salobj import test_utils
from lsst.ts.ATWhiteLightSource.wlsCSC import WhiteLightSourceCSC
from collections import namedtuple


class WhiteLightSourceCSCTests(unittest.TestCase):
    def setUp(self):
        self.csc = WhiteLightSourceCSC(sim_mode=1)
        self.csc.summary_state = salobj.State.ENABLED
        

        # set short cooldown and warmup periods so the tests don't take hours
        self.csc.model.cooldownPeriod = 3
        self.csc.model.warmupPeriod = 3

        self.remote = salobj.Remote(SALPY_ATWhiteLight, index=None)


    def slp(self, watts):
        """wraps the wattage number up in something that looks like id_data
           so these tests can easily call the csc do_setLightPower() method
        """
        dataclass = namedtuple('data', ['setLightPower'])
        id_dataclass = namedtuple('id_data', 'data')
        data = dataclass(watts)
        id_data = id_dataclass(data)
        return id_data

    def testRemotePowerOn(self):
        pass

    def testPowerOn(self):
        """
        Tests bulb wattage ramps to 1200 for 2 sec, then drops to 800.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
        asyncio.get_event_loop().run_until_complete(doit())

    def testPowerOff(self):
        """
        Tests the PowerLightOff command, which sets watts to 0.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
            await self.csc.model.warmup_task
            task = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 0)
        asyncio.get_event_loop().run_until_complete(doit())

    def testSetPower(self):
        """
        Tests bulb wattage setting.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)

            # set to 950 watts
            task = asyncio.ensure_future(self.csc.do_setLightPower(self.slp(950)))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 950)

        asyncio.get_event_loop().run_until_complete(doit())

    def testSetPowerTooLow(self):
        """
        Tests that we power off when we request a wattage <800.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)

            # any setting below 800 should result in 0 watts
            await self.csc.model.warmup_task
            task = asyncio.ensure_future(self.csc.do_setLightPower(self.slp(799)))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 0)
        asyncio.get_event_loop().run_until_complete(doit())

    def testSetPowerTooHigh(self):
        """
        Make sure we get an exception when we set the wattage too high.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            task = asyncio.ensure_future(self.csc.do_setLightPower(self.slp(1201)))
            with self.assertRaises(salobj.ExpectedError):
                await task
        asyncio.get_event_loop().run_until_complete(doit())

    def testCantSetPowerWithBulbOff(self):
        """
        Tests that when we power off, we're not allowed to setLightPower()
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
            await self.csc.model.warmup_task
            offtask = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            await asyncio.sleep(0.5)
            ontask = asyncio.ensure_future(self.csc.do_setLightPower(self.slp(999)))
            with self.assertRaises(salobj.ExpectedError):
                await ontask
            await offtask
        asyncio.get_event_loop().run_until_complete(doit())

    def testCantPowerOnDuringCooldownPeriod(self):
        """
        Tests that when we power off, we're not allowed to power on during
        the cooldown period. Normally this is 5 minutes, but in this test
        it's 3 seconds.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
            await self.csc.model.warmup_task
            offtask = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            await asyncio.sleep(0.5)
            ontask = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            with self.assertRaises(salobj.ExpectedError):
                await ontask
            await offtask
            await self.csc.model.cooldown_task
            ontask2 = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await ontask2
            self.assertEqual(self.csc.model.component.bulbState, 800)
        asyncio.get_event_loop().run_until_complete(doit())

    def testCantPowerOffDuringWarmupPeriod(self):
        """
        Tests that when we power on, we're not allowed to power off during
        the warmup period. Normally this is 15 minutes, but in this test
        it's 3 seconds.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
            task = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            with self.assertRaises(salobj.ExpectedError):
                await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
        asyncio.get_event_loop().run_until_complete(doit())

    def testEmergencyPowerLightOff(self):
        """
        Tests that emergencyPowerLightOff works during the warmup
        period.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            self.assertEqual(self.csc.model.component.bulbState, 0)
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 800)
            task = asyncio.ensure_future(self.csc.do_emergencyPowerLightOff(None))
            await task
            self.assertEqual(self.csc.model.component.bulbState, 0)
        asyncio.get_event_loop().run_until_complete(doit())

    def testCantPowerOffWhileOff(self):
        """
        Tests that we get an error when we try to turn off the bulb
        when it is already off.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            await self.csc.model.warmup_task
            task = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            await task
            task = asyncio.ensure_future(self.csc.do_powerLightOff(None))
            with self.assertRaises(salobj.ExpectedError):
                await task

        asyncio.get_event_loop().run_until_complete(doit())

    def testCantPowerOnWhileOn(self):
        """
        Tests that we get an error when we try to turn on the bulb
        when it is already on.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await task
            await self.csc.model.warmup_task
            task = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            with self.assertRaises(salobj.ExpectedError):
                await task

        asyncio.get_event_loop().run_until_complete(doit())

    def testChangePowerDuringPowerOn(self):
        """
        Tests if we signal a wattage change during the initial ramp-up,
        the ramp-up finishes normally and then we jump to the
        requested wattage.
        """
        test_utils.set_random_lsst_dds_domain()

        async def doit():
            ontask = asyncio.ensure_future(self.csc.do_powerLightOn(None))
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            changetask = asyncio.ensure_future(self.csc.do_setLightPower(self.slp(1105)))
            await asyncio.sleep(0.3)
            self.assertEqual(self.csc.model.component.bulbState, 1200)
            await ontask
            await changetask
            self.assertEqual(self.csc.model.component.bulbState, 1105)
        asyncio.get_event_loop().run_until_complete(doit())


if __name__ == "__main__":
    unittest.main()
