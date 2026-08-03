def resolve_peer_cockpit(peer):
    presence_data = get_presence_data()
    if peer == 'local':
        return resolve_peer_cockpit('local')
    elif peer in presence_data:
        return presence_data[peer]['ip']
    else:
        raise ValueError(f'Unknown peer: {peer}')