def calculate_rsi(data, period):
    delta = (data['close'].diff().fillna(0) > 0).astype(int)
    gains = delta[delta == 1].cumsum()
    losses = -delta[delta == -1].cumsum()
    avg_gain = gains.rolling(window=period, min_periods=1).mean()
    avg_loss = losses.rolling(window=period, min_periods=1).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi