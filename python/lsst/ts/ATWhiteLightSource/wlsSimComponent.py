__all__ = ["WhiteLightSourceComponentSimulator"]

import time
from collections import namedtuple


class WhiteLightSourceComponentSimulator():
    """ A fake version of the White Light Source component that doesn't
        communicate with hardware at all but prints the wattage
        of a simulated WLS Bulb.
        
        Parameters
        ----------
        ip : string
            the IP address of the ADAM 6024 controller
        port : int
            the port number for the ADAM 6024 controller
        
        Attributes
        ----------
        client : ModbusClient
            the pymodbus object representing the ADAM 6024
        bulbHours : float
            uptime of this bulb
        bulbWattHours : float
            uptime in this bulb in watt-hours
        bulbHoursLastUpdate: float
            the time of the last update for bulb uptime
        bulbstate : float
            the current wattage the bulb is at. 
        """


    def __init__(self, ip='140.252.33.160', port=502):
        self.bulbHours = 0  # Read this from EFD when we initialize
        self.bulbWattHours = 0  # This too
        self.bulbHoursLastUpdate = time.time()/3600
        self.bulbState = 0 #current wattage



    def setError(self, id):
        """ Simulates an error of the given type. When the hardware
            enters an error state, the status LED will be red, and
            the error LED will flash a number fo times at 0.5 second
            intervals to indicate one of the following errors,
            followed by a 1.5 second gap, then repeating.

            1 EMERGENCY KILL SWITCH TRIGGERED
            2 TEMPERATURE SWITCH FAULT CHASSIS OVERHEATING
            3 ACCESS DOOR SWITCH NOT SET
            4 LBM_HOT FROM BALLAST INDICATES BALLAST OVERHEATING
            5 USB CABLE REMOVED - DISCONNECTED FROM HOST COMPUTER
            6 AIRFLOW SENSOR DETECTING INADEQUATE COOLING DUE TO LACK
              OF AIRFLOW
            7 BULB DIDN'T EXTINGUISH AFTER INSTRUCTED TO DO SO. ENGAGE
              EMERGENCY KILL SWITCH, WAIT 5 MINUTES, THEN TURN OFF POWER.
              RESTART SOFTWARE, WAIT 1 MINUTE. TURN ON POWER
            8 AIRFLOW CIRCUITRY MALFUNCTION

            Parameters
            ----------
            id : int
                Should be in the range of 1-8.

            Returns
            -------
            None
        """
        while self.redStatusLED:
            i = 0
            while i < id:
                self.errorLED = True
                time.sleep(0.5)
                self.errorLED = False
                time.sleep(0.5)
                i += 1
            time.sleep(1.5)

    def setLightPower(self, watts):
        """ Sets the brightness (in watts) on the white light source.
            We always set the brightness to self.startupWattage for a
            moment (self.startupTime), then step it back down to the
            target wattage.

            Parameters
            ----------
            watts : int or float
                Should be in the range of 800-1200 (inclusive)

            Returns
            -------
            None
        """
        self.bulbState = watts
        self._printBulbState()

    def checkStatus(self):
        """ checks 4 analog inputs to see if any of them have
            voltages in excess of 3.0. If so, that's an error!

        Parameters
        ----------
        None

        Returns
        -------
        errors: List of booleans
        """

        KiloArcStatus = namedtuple('KiloArcStatus', ['wattage','greenLED','blueLED','redLED','errorLED'])
        return KiloArcStatus(self.bulbState, self.greenStatusLED, self.blueStatusLED, self.redStatusLED, self.errorLED)

    def _printBulbState(self):
        print("Simulated WLS bulb set to " + str(self.bulbState) + " watts.")
