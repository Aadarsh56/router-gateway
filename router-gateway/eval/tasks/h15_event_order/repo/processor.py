class EventProcessor:
    def __init__(self):
        self.state = {}

    def handle_create(self, event):
        self.state[event["id"]] = {"value": event["value"], "active": True}

    def handle_update(self, event):
        if event["id"] in self.state and self.state[event["id"]]["active"]:
            self.state[event["id"]]["value"] = event["value"]

    def handle_delete(self, event):
        if event["id"] in self.state:
            self.state[event["id"]]["active"] = False

    def get_active(self):
        return {k: v["value"] for k, v in self.state.items() if v["active"]}
