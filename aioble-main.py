import aioble
import uasyncio as asyncio
import binascii
import bluetooth as bl
import network
import urequests
import json
import time


# Configuración Wi-Fi
SSID = ''
PASSWORD = ''

# Configuración BLE y OBD-II
device = aioble.Device(aioble.ADDR_PUBLIC, "1c:a1:35:69:8d:c5")
UART_SERVICE_UUID = bl.UUID(0xfff0)
UUID_1 = bl.UUID(0xfff1)
UUID_2 = bl.UUID(0xfff2)

# URL del API
API_URL = "http://192.168.100.26:8000/api/company/"

# Funciones
def clear_data(data):
    if data == b'\r>':
        data = None
    return data


def clear_gas(data):
    gas = clear_data(data)
    if gas:
        important_data = data[6:]

        try:
            important_data_str = important_data.decode('utf-8').strip()
            decimal_data = int(important_data_str, 16)
            gas_level = 100/255 * decimal_data
            return f"{gas_level:0.2f}", "%"
        except (ValueError, IndexError) as e:
            print(e)
            return None
    return None


def clear_battery(data):
    battery = clear_data(data)

    if battery:
        important_data = data[6:]

        important_data_str = important_data.decode('utf-8').strip()
        important_data_str = important_data_str.replace(' ', '')

        A = important_data_str[:2]
        B = important_data_str[2:]

        decimal_A = int(A, 16)
        decimal_B = int(B, 16)
        control_module_voltage = (256*decimal_A+decimal_B)/1000

        return control_module_voltage


def check_warnings(gas, voltage):
    warnings = []
    if gas:
        gas_int = gas[:2]
        gas_int = int(gas_int)
        if gas_int < 25:
            warnings.append("low gas level")

        return warnings
    return None


def isready(data):
    for i in data.values():
        if i == False:
            return False

    return True


def error_handle(data):
    exist = False
    number = 0
    data = data.decode("utf-8").strip()
    no_space_data = data.replace(" ", "")
    hexa_num = no_space_data[4:6]
    dec_num = int(hexa_num, 16)
    bin_num = bin(dec_num)[2:]
    msb = int(bin_num[0])

    if msb == 1:
        exist = True
        number = dec_num - 128

    return exist, number

def translate_errors(data):
    data_str = data.decode("utf-8")
    no_space = data_str.replace(" ", "")
    important_data = no_space[2:]
    pairs = []
    table_translations = {
        "0":"P0",
        "1":"P1",
        "2":"P2",
        "3":"P3",
        "4":"C0",
        "5":"C1",
        "6":"C2",
        "7":"C3",
        "8":"B0",
        "9":"B1",
        "A":"B2",
        "B":"B3",
        "C":"U0",
        "D":"U1",
        "E":"U2",
        "F":"U3"
    }
    
    for i in range(3):
        pair = important_data[:4]
        if pair != "0000":
            pairs.append(pair)
        important_data = important_data[4:]
        
    translated_pairs = []
    for pair in pairs:
        first_digit = pair[0]
        translated_first_digit = table_translations.get(first_digit, first_digit) 
        new_pair = translated_first_digit + pair[1:] 
        translated_pairs.append(new_pair)
        
    return translated_pairs


# Funciones asincronas
async def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)

    # Esperar conexión
    while not wlan.isconnected():
        print("Conectando a Wi-Fi...")
        time.sleep(1)

    print("Conectado a Wi-Fi:", wlan.ifconfig())


async def send_to_api(data):
    json_data = json.dumps(data)
    try:
        response = urequests.post(API_URL, data=json_data, headers={
                                  "Content-Type": "application/json"})
        print("Código de estado:", response.status_code)
        print("Respuesta del servidor:", response.text)
        response.close()
    except Exception as e:
        print("Error al enviar datos al API:", e)


async def main():
    try:
        # Conectar a Wi-Fi
        # await connect_wifi()

        # Conectar a dispositivo BLE
        print("Conectando a dispositivo BLE...")
        try:
            connection = await device.connect(timeout_ms=5000)
            print("Conectado a dispositivo BLE")
        except asyncio.TimeoutError:
            print("Timeout al conectar BLE")
            return

        # Descubrir servicios y características
        try:
            print("Descubriendo servicios BLE...")
            uart_service = await connection.service(UART_SERVICE_UUID)
            char_fff1 = await uart_service.characteristic(UUID_1)
            char_fff2 = await uart_service.characteristic(UUID_2)
            print("Servicio UART y características encontradas.")
        except Exception as e:
            print("Error al descubrir servicios:", e)
            await connection.disconnect()
            return

        # Suscribirse a notificaciones
        await char_fff1.subscribe(notify=True)

        # Función para enviar comando y recibir respuesta
        async def send_command_and_get_raw_response(command):
            print(f"Comando: {command}")
            await char_fff1.write((command + "\r\n").encode('utf-8'))
            while True:
                try:
                    # Esperar notificación
                    data = await char_fff1.notified(timeout_ms=20000)
                    print(f"Respuesta: {data}")
                    return data
                except asyncio.TimeoutError:
                    print(
                        f"Tiempo de espera agotado para el comando: {command}")
                except Exception as e:
                    print(f"Error al recibir respuesta para el comando {command}: {e}")
                    break

        # Mantener el proceso en un bucle
        await send_command_and_get_raw_response("ATZ")
        await asyncio.sleep(2)
        await send_command_and_get_raw_response("ATE0")
        await asyncio.sleep(2)

        loop = 0

        flags = {
            'sensor_flag': False,
            'errors_flag': False,
            'gas_flag': False,
            'battery_flag': False,
        }

        data = {
            'sensor': '',
            'errors': {'exist': False,
                       'number': 0,
                       'errors': None
                       },
            'gas': '',
            'battery': '',
            'warnings': '',
        }

        while loop == 0:

            if flags['sensor_flag'] == False:
                sensor_response = await send_command_and_get_raw_response("0902") #vin
                await asyncio.sleep(2)
                print(f"La respuesta al comando AT@2 fue {sensor_response}")
                sensor_response = clear_data(sensor_response)
                if sensor_response:
                    data['sensor'] = sensor_response
                    flags['sensor_flag'] = True

            if flags['errors_flag'] == False:
                error_response = await send_command_and_get_raw_response("0101")
                await asyncio.sleep(2)
                print(f"La respuesta al comando 0101 fue {error_response}")
                exist, number = error_handle(error_response)
                if exist:
                    get_errors = await send_command_and_get_raw_response("03")
                    await asyncio.sleep(2)
                    print(f"Los errores obtenidos fueron {get_errors}")
                    errors = translate_errors(get_errors)
                    data['errors']['exist'] = exist
                    data['errors']['number'] = number
                    data['errors']['errors'] = errors
                    flags['errors_flag'] = True

            if flags['gas_flag'] == False:
                gas_response = await send_command_and_get_raw_response("012F")
                await asyncio.sleep(2)
                print(f"La respuesta al comando 012f fue {gas_response}")
                gas_response = clear_gas(gas_response)
                if gas_response:
                    data['gas'] = gas_response
                    flags['gas_flag'] = True

            if flags['battery_flag'] == False:
                battery_response = await send_command_and_get_raw_response("0142")
                await asyncio.sleep(2)
                print(f"La respuesta al comando 0142 fue {battery_response}")
                battery_response = clear_battery(battery_response)
                if battery_response:
                    data['battery'] = battery_response
                    flags['battery_flag'] = True

            warnings = check_warnings(gas_response, battery_response)
            if warnings:
                data['warnings'] = warnings

            print(data)
            if isready(flags) == True:
                # Enviar datos al API
                await send_to_api(data)
                loop = 1

            # Intervalo entre iteraciones del bucle
            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nInterrupción de teclado detectada. Cerrando...")
    finally:
        # Desconectar BLE si está conectado
        if 'connection' in locals() and connection.is_connected():
            await connection.disconnect()
        print("Desconectado del dispositivo BLE.")
        print("Programa terminado.")


# Ejecutar el programa principal
asyncio.run(main())
