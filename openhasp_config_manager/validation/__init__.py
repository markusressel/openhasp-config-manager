import abc


class Validator(metaclass=abc.ABCMeta):
    """
    Generic interface to implement validators used when validating the configuration.
    """

    @abc.abstractmethod
    def validate(self, data: str):
        """
        Validates the given input data.

        If the input is considered valid, the method will return.

        If the input is considered invalid, an error will be raised further
        detailing the reasons why it is considered invalid.

        :param data: the input data to analyze
        """
        raise NotImplementedError
