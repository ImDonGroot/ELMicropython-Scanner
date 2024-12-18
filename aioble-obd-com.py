import aioble
import uasyncio as asyncio
import binascii
import bluetooth as bl

# Constants
device = aioble.Device(aioble.ADDR_PUBLIC, "1c:a1:35:69:8d:c5")
UART_SERVICE_UUID = bl.UUID(0xfff0)
UUID_1 = bl.UUID(0xfff1)
UUID_2 = bl.UUID(0xfff2)

async def main():
    
    # Conexion
    print("Conectando a dispositivo...")
    try:
        connection = await device.connect(timeout_ms=5000)
        print("Conectado a dispositivo")
    except asyncio.TimeoutError:
        print("Timeout")
        return

    # Descubrir servicios y caracteristicas
    try:
        print("Descubriendo servicios...")
        uart_service = await connection.service(UART_SERVICE_UUID)
        char_fff1 = await uart_service.characteristic(UUID_1)
        char_fff2 = await uart_service.characteristic(UUID_2)
        print("Servicio UART y caracteristicas encontradas.")
    except Exception as e:
        print("Error descubriendo servicios y caracteristicas:", e)
        await connection.disconnect()
        return

    # suscribirte a las notificaciones de fff1
    await char_fff1.subscribe(notify=True)

    # funcion para mandar comandos 
    async def send_command(command):
    
        print(f"Enviando comando: {command}")
        await char_fff1.write((command + "\r\n").encode('utf-8')) #command.encode('utf-8')
    
    # Notification listener con convercion a hex
    async def notification_listener():
        while True:
            try:
                data = await char_fff1.notified(timeout_ms=20000)
                print("Notificación recibida:", data)
            except asyncio.TimeoutError:
                print("Notificación expirada.")
            except Exception as e:
                print("Error de notificación:", e)
                break  

    # Run the notification listener concurrently with sending commands
    asyncio.create_task(notification_listener())
    
    # Sending commands
    await send_command("ATE0") # echo off
    await asyncio.sleep(2)
    await send_command("0902") #pid
    await asyncio.sleep(2)
    await send_command("0101") 
    await asyncio.sleep(2)
    await send_command("03") 
    await asyncio.sleep(2)
    await send_command("012F") 
    await asyncio.sleep(2)
    await send_command("0142") 
    await asyncio.sleep(2)
    
    
#     await send_command("2129") #pid gasolina toyota
#     await asyncio.sleep(2)
    
    # Disconnect after sending commands
    await asyncio.sleep(2)
    #await connection.disconnect()
    #print("Desconectado del dispositivo.")

# Run the main function
asyncio.run(main())

