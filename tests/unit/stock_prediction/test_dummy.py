"""This is a dummy test file."""


def dummy_function():
    """
    Returns a dummy string
    """
    return "Hello, World!"


def test_dummy_function():
    """
    Tests the dummy function.
    """
    assert dummy_function() == "Hello, World!"
