from gevent.hub import Hub
from disco import cli
from raven import Client


IGNORE_ERROR = Hub.SYSTEM_ERROR + Hub.NOT_ERROR


def register_sentry_error_handler(sentry):
    Hub._origin_handle_error = Hub.handle_error

    def custom_handle_error(self, context, type, value, tb):
        if not issubclass(type, IGNORE_ERROR):
            sentry.captureException()
        self._origin_handle_error(context, type, value, tb)

    Hub.handle_error = custom_handle_error


if __name__ == '__main__':
    disco = cli.disco_main()
    sentry = Client(disco.client.config.sentry_dsn)
    sentry.environment = disco.client.config.sentry_environment
    register_sentry_error_handler(sentry)
    try:
        disco.run_forever()
    except:
        sentry.captureException()

