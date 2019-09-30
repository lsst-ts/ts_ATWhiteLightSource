__all__ = ["WhiteLightSourceCSC"]

from lsst.ts import salobj
from wlsModel import WhiteLightSourceModel
from chillerModel import ChillerModel
import pathlib
import asyncio
import time
import enum
from pymodbus.exceptions import ConnectionException


class WLSDetailedState(enum.IntEnum):
    """ For the White Light Source, detailed state is implemented
        as a representation of the state of the KiloArc hardware,
        based on its reported status. As such, there are four 
        possible detailed states:

        OFFLINE:    We are receiving no signal from the KiloArc;
                    the status LED is not illuminated.
        READY:      The KiloArc bulb is either illuminated, or it 
                    is ready to be illuminated. Status LED is
                    green.
        COOLDOWN:   The bulb is off, and KiloArc's internal fans 
                    are active. Status LED is blue. This state 
                    lasts for 5m, and is independent of the 15m 
                    software-enforced cooldown and warmup periods.
        ERROR:      KiloArc is reporting an error. Status LED is 
                    red. This always sends the CSC into a FAULT
                    state. 
        DISCONNECTED:We are unable to determine the state of the
                    KiloArc because we have lost our connection
                    to the ADAM device. 
    """
    OFFLINE = 1
    READY = 2
    COOLDOWN = 3
    ERROR = 4
    DISCONNECTED = 5

class WhiteLightSourceCSC(salobj.ConfigurableCsc):
    """ 
    The White Light Source CSC class

    Parameters
    ----------
    sim_mode : int
        0 to init the CSC to control the actual hardware
        1 to init the CSC in simulation mode
    
    Attributes
    ----------
    model : WhiteLightSourceModel
        the model representing the white light hardware
    detailed_state : WLSDetailedStateEnum
        represents the reported state of the Kiloarc
    telemetry_publish_interval: int/float
        frequency, in seconds, that we publish telemetry
    hardware_listener_interval : int/float
        frequency, in seconds, that we check in on the hardware
    """
    def __init__(self, config_dir=None, initial_state=salobj.State.STANDBY, initial_simulation_mode=0):
        schema_path = pathlib.Path(__file__).resolve().parents[4].joinpath("schema", "whitelight.yaml")
        super().__init__("ATWhiteLight", index=0, schema_path=schema_path, config_dir=config_dir,
                         initial_state=initial_state, initial_simulation_mode=initial_simulation_mode)
        self.model = WhiteLightSourceModel()
        
        self.detailed_state = WLSDetailedState.OFFLINE

        self.telemetry_publish_interval = 5
        self.hardware_listener_interval = 2
        self.chillerModel = ChillerModel()

        #setup asyncio tasks for the loops
        done_task = asyncio.Future()
        done_task.set_result(None)
        self.telemetryLoopTask = done_task
        self.kiloarcListenerTask = done_task
        self.config = None

        asyncio.ensure_future(self.stateloop())
        self.kiloarcListenerTask = asyncio.ensure_future(self.kiloarcListenerLoop())

    @staticmethod
    def get_config_pkg():
        return("ts_config_atcalsys")

    async def configure(self, config):
        self.config = config

    async def begin_standby(self, id_data):
        """ When we leave fault state to enter standby, we 
            need to make sure that the hardware isn't still
            reporting errors
        """
        print("begin_standby()")
        # don't let the user leave fault state if the KiloArc
        # or chiller is reporting an error
        if self.summary_state == salobj.State.FAULT:
            if self.model.component.checkStatus().redLED:
                raise RuntimeError("Can't enter Standby state while KiloArc still reporting errors")
        if self.summary_state == salobj.State.DISABLED:
            self.telemetryLoop.cancel()
            self.kiloarcListenerTask.cancel()
            await self.chillerModel.disconnect()
        

    async def begin_enable(self, id_data):
        """ Upon entering ENABLE state, we need to start 
            the telemetry and hardware listener loops.
        """
        print("begin_enable()")
        

    async def begin_start(self, id_data):
        """ Executes during the STANDBY --> DISABLED state
            transition. Confusing name, IMHO. 
        """
        print("begin_start()")
        self.telemetryLoopTask = asyncio.ensure_future(self.telemetryLoop())
        self.kiloarcListenerTask = asyncio.ensure_future(self.kiloarcListenerLoop())
        await self.chillerModel.connect()

    async def begin_disable(self, id_data):
        print("begin_disable()")

    async def implement_simulation_mode(self, sim_mode):
        """ Swaps between real and simulated component upon request.
        """
        print("sim mode " + str(sim_mode))
        if sim_mode == 0:
            self.model.component = self.model.realComponent
        else:
            self.model.component = self.model.simComponent

    async def do_powerLightOn(self, id_data):
        """ Powers the light on. It will go to 1200 watts, then drop
            back down to 800. Not available of the lamp is still
            cooling down.
        """
        self.assert_enabled("powerLightOn")
        await self.model.powerLightOn()

    async def do_powerLightOff(self, id_data):
        """ Powers the light off. Not available of the lamp is still 
            warming up.
        """
        await self.model.setLightPower(0)

    async def do_setLightPower(self, id_data):
        """ Sets the light power. id_data must contain a topic that 
            specifies the wattage, between 800 and 1200. Numbers 
            below 800 will be treated like a powerLightOff command.
        """
        self.assert_enabled("setLightPower")
        await self.model.setLightPower(id_data.data.setLightPower)

    async def do_emergencyPowerLightOff(self, id_data):
        """ Powers the light off. This one ignores the warmup period
            that the CSC normally enforces.
        """
        await self.model.emergencyPowerLightOff()

    async def do_setChillerTemperature(self,id_data):
        """ Sets the target temperature for the chiller

                Parameters
                ----------
                temperature : float

                Returns
                -------
                None
        """
        self.chillerModel.setControlTemp(id_data.data.setChillerTemperature)

    async def do_startCooling(self,id_data):
        """ Powers chiller on

                Parameters
                ----------
                None

                Returns
                -------
                None
            """
        pass

    async def do_stopCooling(self,id_data):
        """ powers chiller off. Not available when bulb is on. 

                Parameters
                ----------
                None

                Returns
                -------
                None
            """
        pass

    async def stateloop(self):
        """
        periodically prints the current state. For debug
        """
        while True:
            print("current state:  "+str(self.summary_state))
           # print("detailed state: "+str(self.detailed_state))
           # print(self.kiloarcListenerTask)
           # print(self.telemetryLoopTask)
            await asyncio.sleep(1)


    async def kiloarcListenerLoop(self):
        """ Periodically checks with the component to see if the wattage
            and/or the hardware's "status light" has changed. If so, we
            publish an event to SAL. Unlike the LEDs, the wattage isn't
            *actually* read from the hardware; we only know what wattage
            the CSC is requesting.
        """
        # if we can't connect to the ADAM, stop loops and go to FAULT state
        # and DISCONNECTED detailed state.
        try:
            previousState = self.model.component.checkStatus()
        except ConnectionException:
            self.summary_state = salobj.State.FAULT
            self.detailed_state = WLSDetailedState.DISCONNECTED
            self.telemetryLoopTask.cancel()
            self.kiloarcListenerTask.cancel() #TODO do we really want to stop this one?
        
        while True:
            #if we lose connection to the ADAM, stop loops and go to FAULT state
            try:
                currentState = self.model.component.checkStatus()
                if currentState != previousState:
                    print("Voltage change detected! \n" + str(currentState))
                    self.evt_whiteLightStatus.set_put(
                        wattageChange = float(currentState.wattage),
                        coolingDown = currentState.blueLED,
                        acceptingCommands = currentState.quitLED,
                        error = currentState.redLED,
                    )
                # update detailed state
                if currentState.greenLED:
                    self.detailed_state = WLSDetailedState.READY
                elif currentState.blueLED:
                    self.detailed_state = WLSDetailedState.COOLDOWN
                elif currentState.redLED:
                    self.detailed_state = WLSDetailedState.ERROR
                else:
                    self.detailed_state = WLSDetailedState.OFFLINE
                previousState = currentState
            except ConnectionException:
                self.summary_state = salobj.State.FAULT
                self.detailed_state = WLSDetailedState.DISCONNECTED
                self.telemetryLoopTask.cancel()
                self.kiloarcListenerTask.cancel()
            

            #if the KiloArc error light is on, put the CSC into FAULT state   
            if currentState.redLED:
                try:
                    if self.model.bulb_on:
                        await self.model.emergencyPowerLightOff()
                except salobj.ExpectedError as e:
                    print("Attempted emergency shutoff of light, but got error: "+ str(e))
                self.summary_state = salobj.State.FAULT
                self.detailed_state = WLSDetailedState.ERROR

            print("HW Loop running")
            await asyncio.sleep(self.hardware_listener_interval)

    async def telemetryLoop(self):
        """ Publish WLS Telemetry. This includes:
                bulb uptime (hours)
                bulb uptime (watt-hours)
                Chiller fan speed, coolant temperature

            Parameters
            ----------
            None

            Returns
            -------
            None
        """
        while True:
            # Kiloarc

            # calculate uptime and wattage since the last iteration of this loop
            lastIntervalUptime = time.time()/3600 - self.model.component.bulbHoursLastUpdate
            lastIntervalWattHours = lastIntervalUptime * self.model.component.bulbState

            # if the bulb is on, update the tracking variables in the component
            if self.model.bulb_on:
                self.model.component.bulbHours += lastIntervalUptime
                self.model.component.bulbWattHours += lastIntervalWattHours

            # set time of last update to current time
            self.model.component.bulbHoursLastUpdate = time.time()/3600

            # publish telemetry
            self.tel_bulbhour.set_put(bulbHours=float(self.model.component.bulbHours))
            self.tel_bulbWatthour.set_put(bulbHours=float(self.model.component.bulbWattHours))

            # Chiller

            self.tel_chillerFanSpeed.set(fan1Speed=int(self.chillerModel.fan1speed))
            self.tel_chillerFanSpeed.set(fan2Speed=int(self.chillerModel.fan2speed))
            self.tel_chillerFanSpeed.set(fan3Speed=int(self.chillerModel.fan3speed))
            self.tel_chillerFanSpeed.set(fan4Speed=int(self.chillerModel.fan4speed))
            self.tel_chillerFanSpeed.put()



            print("Telemetry Loop Running")
            await asyncio.sleep(self.telemetry_publish_interval)
