import logging

class Log:
    _instance = None  # Class-level variable to hold the single instance

    def __new__(cls, level='INFO', filename=None):
        # Create instance if it doesn't exist
        if cls._instance is None:
            cls._instance = super(Log, cls).__new__(cls)
            cls._instance.logger = cls._instance._get_logger(level, filename)
        return cls._instance


    def __init__(self, level=logging.INFO, filename=None):
        self.logger = self._get_logger(level, filename)


    def _get_logger(self, level, filename):
        logger = logging.getLogger(__name__)
        
        if logger.hasHandlers():
            for handler in logger.handlers:
                handler.setLevel(level)
            logger.setLevel(level)
            return logger

        logger.setLevel(level)
        
        if filename:
            handler = logging.FileHandler(filename)
        else:
            handler = logging.StreamHandler()

        handler.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger


    def _map_level(self, level):
        level_mapping = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARN': logging.WARNING,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'FATAL': logging.CRITICAL,
            'CRITICAL': logging.CRITICAL,
        }
        return level_mapping.get(level.upper(), logging.INFO)


    def setLevel(self, level):
        level = self._map_level(level)
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)


    def debug(self, message):
        self.logger.debug(message)


    def info(self, message):
        self.logger.info(message)


    def warning(self, message):
        self.logger.warning(message)


    def error(self, message):
        self.logger.error(message)


    def critical(self, message):
        self.logger.critical(message)

# Example usage
if __name__ == '__main__':
    # Create Log instance with INFO level
    log = Log('test_logger')
    log.info('This is an INFO message.')
    
    # Update Log instance to DEBUG level
    log.setLevel(logging.DEBUG)
    log.debug('This is a DEBUG message.')  # Now it will be logged

