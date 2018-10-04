import re
import evdev
import time
import json
import threading

import USB

try:
    import RPi.GPIO as GPIO
except RuntimeError:
    print("Need root priviledges.")
    exit(1)

# VID and PID of the USB Device
ids = ["c216","0180"]

#Regex used to search ASU ID's
cardRegex = r";601744(\d{10})\d(\d{10})\?"
#Regex used to search USB Physical Addresses
usbRegex = r"usb-.+-(\d\.\d)\/input0"

portDevices = [
    {
        "name": "cab_left",
        "port": "1.5",
        "gpio_lock": 7,
        "gpio_led_green": 13,
        "gpio_led_red": 33,
    },
    {
        "name": "cab_right",
        "port": "1.4",
        "gpio_lock": 11,
        "gpio_led_green": 29,
        "gpio_led_red": 31,
    }
]
portDevices_mutex = threading.Lock()

#break out all relay GPIO pins for simplicity
gpioList = [7,11,13,15,29,31,33,35]

authorizedUsers = {}
authorizedUsers_mutex = threading.Lock()

def getUsers():
    #no threads started at this point so locking is needless
    global authorizedUsers
    try:
        with open("./user.json", "r") as f:
            authorizedUsers = json.loads(f.read())
    except FileNotFoundError:
        open("user.json", 'w+')

def runUSB(port, reader):
    print("starting", port['name'])

    portDevices_mutex.acquire(True)
    lock_pin  = port['gpio_lock']
    green_led = port['gpio_led_green']
    red_led   = port['gpio_led_red']
    portDevices_mutex.release()

    reader.grabDevice()
    while True:
        #this call is blocking
        user_id = reader.extractID(reader.interpretEvents(reader.readData()), cardRegex)

        authorizedUsers_mutex.acquire(True)
        for x in authorizedUsers["users"]:
            if x["ID"] == user_id:
                onSuccess(lock_pin, green_led)
                break
        else:
            onFail(red_led)
        authorizedUsers_mutex.release()

    reader.ungrabDevice()

def initGPIO():
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    GPIO.setup(gpioList, GPIO.OUT, initial=1)


def onSuccess(lock_pin, green_pin):
    GPIO.output(green_pin, 0)
    GPIO.output(lock_pin, 0)
    time.sleep(5)
    GPIO.output(green_pin, 1)
    GPIO.output(lock_pin, 1)

def onFail(red_pin):
    GPIO.output(red_pin, 0)
    time.sleep(3)
    GPIO.output(red_pin, 1)

if __name__ == "__main__":
    initGPIO()
    getUsers()

    #get all USB Devices in an iterable List
    for device in [evdev.InputDevice(fn) for fn in evdev.list_devices()]:
        #filter the ones with a particular VID and PID
        if hex(device.info.vendor)[2:].zfill(4) == ids[0] and \
           hex(device.info.product)[2:].zfill(4) == ids[1]:
            # Use regex to extract bus and port info
            deviceBus = re.search(re.compile(usbRegex), device.phys).group(1)
            for portObj in portDevices:
                #if the busport info match one of the expected devices, spin up a handler thread
                if portObj['port'] == deviceBus:
                    #we don't save the the thread object here because we never need to touch it after creating it
                    threading.Thread(target=runUSB, args=(portObj, USB.Reader(device))).start()
