'''
The RaspberryPi controller. Interfaces with the Arduino via serial,
    and the mission control PC over a wireless TCP connection.
Made: 10/9/25
Edited: 10/23/25
Authors: James Meyers
'''

# Standard Imports
import time
import socket

# Third Part Imports
import serial

def connection_loop(arduino:serial.Serial, client_socket:socket.socket) -> bool:
    '''
    Main communication loop with Arduino, RaspberryPi, and mission control PC

    '''
    # Grab input from client and send to Arduino
    arduino_out = client_socket.recv(1024).decode().strip()
    if arduino_out == 'x':
        return False
    arduino.write(arduino_out.encode("utf-8"))

    time.sleep(0.1)

    # Read output from arduino and send to client
    arduino_in = arduino.read_all()
    client_socket.sendall(arduino_in)


def initialize_connection(server_socket:socket.socket) -> socket.socket:
    '''
    Starts connection setup for a client.
    Used for both initial connection and reconnects.
    '''

    # Wait for client to connect
    server_socket.listen()
    print("Waiting for connection")

    # Handshake with client and return the socket
    client_socket, addr = server_socket.accept()
    print("Client connected at " + str(addr))
    return client_socket

def initialize_arduino() -> serial.Serial:
    '''
    Starts connection setup for Arduino.
    Note: if the arduino comes discconnected in any physical way there is no way to reconnect!
    '''

    # Open Arduino serial port and return the port
    arduino = serial.Serial(port='COM3', baudrate=9600)
    print("Connecting to Arduino...")
    time.sleep(1)
    print("Connected to Arduino")
    arduino.read_all()
    return arduino
    
if __name__ == '__main__':
    # Create Server
    server_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    server_socket.bind(("10.16.62.101", 60500))

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
                arduino = initialize_arduino()
                client_socket.sendall("Arduino Connected".encode('utf-8'))
                arduino_state = 1
            
            if connection_loop(arduino, client_socket) is False:
                break

        except serial.SerialException:
            if arduino_recconect_counter > 5:
                break
            print("Arduino Serial Error, Attempting Reconnect")
            time.sleep(1)
            arduino_recconect_counter += 1
            arduino_state = 0
            
        except ConnectionError:
            print("Client Disconnected")
            client_state = 0