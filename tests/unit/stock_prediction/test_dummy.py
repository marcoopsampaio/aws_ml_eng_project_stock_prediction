"""This is a dummy test file."""


def dummy_function():
    """
    Returns a dummy string.

    :return:
    """
    return "Hello, World!"


def test_dummy_function():
    """
    Tests the dummy function.

    :return:
    """
    assert dummy_function() == "Hello, World!"
