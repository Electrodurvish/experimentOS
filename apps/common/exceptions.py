from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        if not isinstance(response.data, dict):
            response.data = {"detail": response.data}
        response.data["status_code"] = response.status_code
    return response


class InvalidTransitionError(Exception):
    pass
