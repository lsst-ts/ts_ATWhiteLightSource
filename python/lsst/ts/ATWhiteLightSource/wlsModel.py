__all__ = ["WhiteLightSourceModel"]

import time
import asyncio

from .wlsComponent import WhiteLightSourceComponent
from .wlsSimComponent import WhiteLightSourceComponentSimulator
from lsst.ts import salobj


class WhiteLightSourceModel():
    """ 
    The White Light Source Model. This keeps track of the state of
    the Kiloarc, and enforces cooldown and warmup periods. 

    Attributes
    ----------
    realComponent : WhiteLightSourceComponent
        the hardware communication class. Needs an IP and port
    simComponent : WhiteLightSourceComponentSimulator
        simulates the real component, but doesn't talk to hardware
    component : one of the two above classes
        points to whichever of the above components we're actually using
    startupWattage : float 800-1200
        when we start the bulb, it initially goes to this wattage
    defaultWattage : float 800-1200
        after the startup wattage, we transition to the default
    startupTime : float
        how log does startupWattage last?
    on_task : asyncio.Future
        keeps track of whether we are currently turning on
    warmup_task : asyncio.Future
        keeps track of whether we are currently in the warmup period
    cooldown_task : asyncio.Future
        keeps track of whether we are currently in the cooldown period
    off_time : float
        the time the bulb was last turned off
    on_time : float
        the time the bulb was last turned on
    cooldownPeriod : float
        how long to we wait after turning off before we can turn back on
    warmupPeriod : float
        how long do we wait after turing on before we can turn back off
    """
    
    def __init__(self):
        self.realComponent = WhiteLightSourceComponent()
        self.simComponent = WhiteLightSourceComponentSimulator()
        self.component = self.simComponent
        self.startupWattage = 1200
        self.defaultWattage = 800
        self.startupTime = 2
        done_task = asyncio.Future()
        done_task.set_result(None)
        self.on_task = done_task
        self.warmup_task = done_task
        self.cooldown_task = done_task
        self.bulb_on = False
        self.off_time = None
        self.on_time = None
        self.cooldownPeriod = 900
        self.warmupPeriod = 900

    async def powerLightOn(self):
        """ Signals the Horiba device to power light on.
            We always set the brightness to self.startupWattage for a
            moment (self.startupTime), then step it back down to the
            default.

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        if not self.cooldown_task.done():  # are we in the cooldown period?
            elapsed = time.time() - self.off_time
            remaining = self.cooldownPeriod - elapsed
            description = "Can't power on bulb during cool-off period. Please wait "
            raise salobj.ExpectedError(description + str(remaining) + " seconds.")
        if self.bulb_on:
            raise salobj.ExpectedError("Can't power on when we're already powered on.")
        self.component.setLightPower(self.startupWattage)
        self.on_time = time.time()
        self.warmup_task = asyncio.ensure_future(asyncio.sleep(self.warmupPeriod))
        self.bulb_on = True
        self.on_task = asyncio.ensure_future(asyncio.sleep(self.startupTime))
        await self.on_task
        self.component.setLightPower(self.defaultWattage)

    async def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.
            There are lots of constraints.
            1 When we turn the bulb on (>800w) we aren't allowed to turn
              it off for 15m because the Hg inside needs to fully evaporate
              But we can overrride.
            2 When we turn the bulb off, we need to wait 15m for the Hg to
              recondense before we can turn it on again.
            3 When we turn on, we go to maximum brightness for 2 seconds and
              then drop back down.
            4 1200w is the maximum brightness, and requesting higher will
              produce an error.
            5 800w is the minimum, and requesting lower is the same as
              requesting to power off.

            Parameters
            ----------
            watts : int or float
                Should be <= 1200. Values under 800 power the light off entirely.

            Returns
            -------
            None
        """
        # TODO: report watts as telemetry (or events?)
        if watts > 1200:
            raise salobj.ExpectedError(f"Wattage {watts} too high (over 1200)")
        if watts < 800:
            # turn bulb off
            if not self.warmup_task.done():
                description = "Can't power off bulb during warm-up period. Please wait "
                elapsed = time.time() - self.on_time
                remaining = self.warmupPeriod - elapsed
                raise salobj.ExpectedError(description + str(remaining) + " seconds.")
                
            if self.bulb_on:
                self.cooldown_task = asyncio.ensure_future(asyncio.sleep(self.cooldownPeriod))
                self.component.setLightPower(0)
                self.bulb_on = False
                self.off_time = time.time()
            else:
                raise salobj.ExpectedError("Bulb is already off")
        else:
            # this executes when watts are inside the 800-1200 range
            if not self.bulb_on:
                raise salobj.ExpectedError("You must turn the light on before setting light power.")
            if not self.on_task.done():
                await self.on_task
                self.component.setLightPower(watts)
            else:
                self.component.setLightPower(watts)
                self.bulb_on = True

    async def emergencyPowerLightOff(self):
        """Signals the device to power off immediately, ignoring the 15m
           warmup period. The manufacturer warns that this can significantly
           reduce the life of the bulb.
        """
        if self.bulb_on:
            self.cooldown_task = asyncio.ensure_future(asyncio.sleep(self.cooldownPeriod))
            self.component.setLightPower(0)
            self.bulb_on = False
            self.off_time = time.time()
        else:
            raise salobj.ExpectedError("Bulb is already off")