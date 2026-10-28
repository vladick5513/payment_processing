class WebhookError(Exception):
    pass


class WebhookTransportError(WebhookError):
    pass


class WebhookResponseError(WebhookError):
    pass
