#!/usr/bin/env python

def handle_ceo_mind_request(prompt):
    # Forward to the peer's /message endpoint
    return forward_to_peer('/message', prompt)

# Define handlers for each CEO
handlers = {
    '/ceo_mind/wren': lambda prompt: handle_ceo_mind_request(prompt),
    '/ceo_mind/tp_pip': lambda prompt: handle_ceo_mind_request(prompt),
    '/ceo_mind/acer_cass': lambda prompt: handle_ceo_mind_request(prompt)
}

# Example route handler for /ceo_mind/wren
@app.route('/ceo_mind/wren', methods=['POST'])
def wren_message_handler():
    return handlers['/ceo_mind/wren'](request.json.get('prompt'))