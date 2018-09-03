from gevent.hub import Hub
from disco import cli


IGNORE_ERROR = Hub.SYSTEM_ERROR + Hub.NOT_ERROR



    Hub.handle_error = custom_handle_error


if __name__ == '__main__':
    disco = cli.disco_main()
    
    try:
        disco.run_forever()
   

