// Custom Trading Annex integration script
const tradingAnnex = require('./trading_annex');

// Initialize the Trading Annex module
tradingAnnex.init();

// Add custom features and layout
tradingAnnex.addFeature('real-time trading');
tradingAnnex.addFeature('portfolio analysis');
tradingAnnex.addFeature('risk management');

// Set the layout to Wren's design
tradingAnnex.setLayout('wren_trading_annex.md');