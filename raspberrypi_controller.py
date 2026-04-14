'''
The RaspberryPi controller. Interfaces with the Arduino via serial,
    and the mission control PC over a wireless TCP connection.
Made: 10/9/25
Edited: 10/02/26
Authors: James Meyers
Co-Author: Tausif Ahmed
'''

# Standard Imports
import time
import socket
import glob

# Third Part Imports
import serial

# Constants
HOST = "0.0.0.0" # listen on all interfaces, so MCC can connect over Wi-Fi/Ethernet
PORT = 60500 # Must match what MCC is trying to connect to
BAUD = 57600 # Higher = faster Arduino response, but going past a certain point can increase instability

# Global Vars
start_time = time.perf_counter() * 1000

def find_serial_ports () -> list[str]:
    '''
    Finds the names of the USB ports that the Arduinos use
    '''

    # Auto-detect the Arduino serial port on Pi
    ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
    if not ports:
        raise RuntimeError("No Arduino detected (/dev/ttyACM* or /dev/ttyUSB*).")
    return ports

def initialize_arduino() -> tuple:
    '''
    Starts connection setup for Arduinos on the PI.
    Searches through the list of Arduinos and identifies them based of off
    what they return when powered on.
    Also checks that they both are working and connected.
    '''

    # Open Arduino serial port and return the port
    # Assign the auto-detected Arduino ports
    ports = find_serial_ports()
    right_arduino = left_arduino = linear_arduino = None
    # Searching through the ports
    for port in ports:
        temp = serial.serial_for_url(url=port, baudrate=BAUD, timeout=0.1, do_not_open = True)
        # Sometimes the Arduinos keep running after being reset, this just manually resets them to clear the input stream so that they can be identified.
        temp.dtr = False
        temp.rts = False
        temp.open()
        temp.reset_input_buffer()
        time.sleep(0.1)
        temp.dtr = True
        temp.rts = True
        time.sleep(2)
        # Get the response which identifies the arduino as either right, left or linear.
        response = temp.read_until('\n').decode('utf-8').strip()
        if response == "right":
            right_arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        elif response == "left":
            left_arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        elif response == "linear":
            linear_arduino = serial.Serial(port=port, baudrate=BAUD, timeout=0.1)
        
        print(f"Connecting to {response}-Arduino on {port}...")

    # Allow Arduinos to reset
    time.sleep(1)
    # Tests that they are indeed connecected.
    right_arduino.reset_input_buffer()
    left_arduino.reset_input_buffer()
    linear_arduino.reset_input_buffer()
    print("Connected to Arduinos")
    return right_arduino, left_arduino, linear_arduino

def initialize_connection(server_socket: socket.socket) -> socket.socket:
    '''
    Starts connection setup for a client.
    Used for both initial connection and reconnects.
    '''

    # Wait for client to connect
    server_socket.listen()
    print("Waiting for MCC connection")

    # Handshake with client and return the socket
    client_socket, addr = server_socket.accept()
    print("Client connected at " + str(addr))

    # Stops the connection loop from waiting for a input from the MCC allowing data to freely move up to it.
    client_socket.setblocking(False)

    return client_socket

def connection_loop(right_arduino: serial.Serial, left_arduino: serial.Serial, linear_arduino: serial.Serial, client_socket: socket.socket) -> bool:
    '''
    Main communication loop with Arduino, RaspberryPi, and mission control PC
    '''

    # Used for syncing the heartbeat
    global start_time

    # Grab input from client and send to Arduino
    # TCP data can include a partial multi-byte character or random bytes (rare, but it happens).
    # .decode() can throw a UnicodeDecodeError and crash the loop
    # "errors=ignore" keeps the bridge running even if one packet contains a weird byte
    try:
        arduino_out = client_socket.recv(1024).decode(errors="ignore").strip()
        # Once again just stops the loop from waiting for a input
    except BlockingIOError:
        arduino_out = ""

    # Seperates lumped up commands into one-liners
    for line in arduino_out.split(sep="@"):
        line = line.strip()

         # Stops empty lines from messing anything up
        if not line:
            continue

        # comma check (to prevent crashes)
        # UDP does not guarantee to receive the full message properly
        # now instead of crashing, it logs and skips that part
        if "," not in line and ";" not in line:
            print(f"[Pi] Bad line (no comma or semicolon): {line}")
            continue

        # "1" to limit the number of splits, in case there is an extra comma
        # Also ensures that arriving data is in correct format
        values, target_group = line.split(';', 1)
        values = values.strip()
        # Target groups replaced the lookup table as we are using the sticks primarily for everything.
        # Target groups 0 is for driving, 1 is for bucket movement, 2 or greater can be for other buttons if needed.
        target_group = target_group.strip()
        values = values.split(',', 1)

        # Checks if the stick postitions are a integer as everything on the Arduino assumes that.
        try:
            ivalue = int(float(values[0]))
            ivalue = int(float(values[1]))
        except ValueError:
            print(f"[Pi] Bad value: {ivalue} in line {line}")
            continue

        # Use target group to determine destination
        # The left Arduino also controls the linear actuators so we send a 0 or 1 to tell it to move either or.
        if target_group is "0":
            left_arduino.write(f"{values[0]},{values[1]}\n".encode('utf-8'))
            right_arduino.write(f"{values[0]},{values[1]}\n".encode('utf-8'))
        elif target_group is "1":
            linear_arduino.write(f"{values[0]},{values[1]}\n".encode('utf-8'))
        elif target_group is "2":
            return False


        print(f"Target Group: {target_group}, Values: {values}")

    # Sleep for a millisecond to allow data to be properly updated and sent, this may have to be increased but works for now.
    time.sleep(0.001)

    # Read output from Arduino and send to client
    if right_arduino.in_waiting > 0:
        right_arduino_output = right_arduino.readline().decode('utf-8')
        print(f"[Right Arduino]: {right_arduino_output}")
        client_socket.sendall(f"[Right Arduino]: {right_arduino_output}".encode('utf-8'))

    if left_arduino.in_waiting > 0:
        left_arduino_output = left_arduino.readline().decode('utf-8')
        print(f"[Left Arduino]: {left_arduino_output}")
        client_socket.sendall(f"[Left Arduino]: {left_arduino_output}".encode('utf-8'))

    if linear_arduino.in_waiting > 0:
        linear_arduino_output = linear_arduino.readline().decode('utf-8')
        print(f"[Linear Arduino]: {linear_arduino_output}")
        client_socket.sendall(f"[Linear Arduino]: {linear_arduino_output}".encode('utf-8'))

    # Used to send the heartbeat every 100 ms, may not be neccesary as the data from the arduinos could serve the same purpose
    if (time.perf_counter() * 1000) - start_time > 100:
        print("RPI Alive")
        client_socket.sendall("RPI Alive".encode('utf-8'))
        start_time = time.perf_counter() * 1000

if __name__ == '__main__':
    # Create Server
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # in case we quickly restart the script, this avoids address already in use error
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Hardcoding a specific IP could break when the Pi connects to a different network
    # 0.0.0.0 listen on whatever IP the Pi currently has
    server_socket.bind((HOST, PORT))
    print(f"[Pi] Listening on {HOST}:{PORT}")

    # Initialize vars
    arduino_state = 0
    client_state = 0
    arduino_recconect_counter = 0

    # This is the main program loop
    # Note: This will probably have to be changed if we want to control the robot without a keyboard
    while True:
        # Checks to make sure everything is connected each loop
        try:
            if client_state == 0:
                client_socket = initialize_connection(server_socket)
                client_state = 1

            if arduino_state == 0:
                right_arduino, left_arduino, linear_arduino = initialize_arduino()
                # Simple exception handler in case MCC disconnects at any moment, it prevents a crash during reconnection
                try:
                    client_socket.sendall("Arduinos Connected".encode('utf-8'))
                except Exception:
                    pass
                arduino_state = 1
                arduino_recconect_counter = 0

            if connection_loop(right_arduino, left_arduino, linear_arduino, client_socket) is False:
                client_socket.close()
                client_state = 0
        # changed a couple of things to make the errors print the reasons
        except serial.SerialException as e:
            if arduino_recconect_counter > 5:
                print("[Pi] Arduino reconnect attempts, exiting...")
                break
            print(f"[Pi] Arduino Serial Error: {e} | Attempting Reconnect")
            time.sleep(1)
            arduino_recconect_counter += 1
            arduino_state = 0

        except ConnectionError:
            print("Client Disconnected")
            client_state = 0
