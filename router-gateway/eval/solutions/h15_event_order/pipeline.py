from processor import EventProcessor

def process_events(events):
    proc = EventProcessor()
    for event in events:
        getattr(proc, f"handle_{event['type']}")(event)
    return proc.get_active()
