import React, { useState, useEffect } from 'react';
import './App.css';
import Chatbot from './components/Chatbot';
import OffersGrid from './components/OffersGrid';
import PreviousOffers from './components/PreviousOffers';

function App() {
  const [offers, setOffers] = useState([]);
  const [selectedOffer, setSelectedOffer] = useState(null);
  const [isChatbotOpen, setIsChatbotOpen] = useState(false);
  const [currentRequest, setCurrentRequest] = useState(null);
  const [notification, setNotification] = useState(null);

  const handleLoanRequest = async (loanData) => {
    try {
      setCurrentRequest(loanData);

      const response = await fetch('http://localhost:8001/process_loan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(loanData),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || 'Failed to process loan request');
      }

      setSelectedOffer(result);
      fetchOffers();
    } catch (error) {
      console.error('Error processing loan:', error);
      alert(`Error: ${error.message}`);
    }
  };

  const fetchOffers = async () => {
    try {
      const response = await fetch('http://localhost:8001/offers');
      if (response.ok) {
        const data = await response.json();
        if (data.loan_requests && data.loan_requests.length > 0) {
          const latestRequest = data.loan_requests[data.loan_requests.length - 1];
          setOffers(latestRequest.offers || []);
        }
      }
    } catch (error) {
      console.error('Error fetching offers:', error);
    }
  };

  useEffect(() => {
    fetchOffers();
  }, []);

  const showNotification = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 5000);
  };

  const hideNotification = () => {
    setNotification(null);
  };

  return (
    <div className="App">
      {notification && (
        <div className={`notification-banner ${notification.type}`}>
          <span>{notification.message}</span>
          <button className="notification-close" onClick={hideNotification}>×</button>
        </div>
      )}

      <header className="App-header">
        <h1>WFAP Credit Negotiation System</h1>
        <p>AI-powered loan evaluation and comparison</p>
      </header>

      <main className="App-main">
        {currentRequest && (
          <div className="current-request">
            <h2>Current Loan Request</h2>
            <pre className="json-display">{JSON.stringify(currentRequest, null, 2)}</pre>
          </div>
        )}

        {selectedOffer && offers.length > 0 && (
          <div className="best-offers-section">
            <h2>Best Loan Offers</h2>
            <div className="best-offers-card">
              {currentRequest && (
                <div className="loan-request-summary">
                  <h3>Your Loan Request</h3>
                  <div className="request-details">
                    <p><strong>Amount:</strong> ${currentRequest.amount.toLocaleString()}</p>
                    <p><strong>Duration:</strong> {currentRequest.duration} months</p>
                    <p><strong>Purpose:</strong> {currentRequest.purpose}</p>
                    {currentRequest.expected_income > 0 && (
                      <p><strong>Expected Income:</strong> ${currentRequest.expected_income.toLocaleString()}</p>
                    )}
                  </div>
                </div>
              )}

              <div className="best-offers-list">
                <h3>Recommended Offers</h3>
                <div className="offers-comparison">
                  {offers
                    .filter(offerData => offerData.offer.amount_approved > 0)
                    .sort((a, b) => {
                      if (b.offer.amount_approved !== a.offer.amount_approved) {
                        return b.offer.amount_approved - a.offer.amount_approved;
                      }
                      return a.offer.interest_rate - b.offer.interest_rate;
                    })
                    .slice(0, 3)
                    .map((offerData, index) => (
                      <div key={index} className={`best-offer-item ${offerData.bank_id === selectedOffer.selected_bank ? 'recommended' : ''}`}>
                        <div className="offer-header">
                          <h4>{offerData.bank_name}</h4>
                          {offerData.bank_id === selectedOffer.selected_bank && (
                            <span className="recommended-badge">★ Recommended</span>
                          )}
                        </div>
                        <div className="offer-metrics">
                          <div className="metric">
                            <span className="label">Amount:</span>
                            <span className="value">${offerData.offer.amount_approved.toLocaleString()}</span>
                          </div>
                          <div className="metric">
                            <span className="label">Rate:</span>
                            <span className="value">{(offerData.offer.interest_rate * 100).toFixed(2)}%</span>
                          </div>
                          <div className="metric">
                            <span className="label">Carbon Rate:</span>
                            <span className="value">{(offerData.offer.carbon_adjusted_rate * 100).toFixed(2)}%</span>
                          </div>
                          <div className="metric">
                            <span className="label">Period:</span>
                            <span className="value">{offerData.offer.repayment_period} months</span>
                          </div>
                        </div>
                        <div className="offer-summary">
                          <p>{offerData.offer.esg_summary}</p>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </div>
        )}

        <OffersGrid offers={offers} onOffersUpdate={setOffers} onNotification={showNotification} />

        <PreviousOffers />
      </main>

      <Chatbot
        isOpen={isChatbotOpen}
        onToggle={() => setIsChatbotOpen(!isChatbotOpen)}
        onLoanRequest={handleLoanRequest}
      />
    </div>
  );
}

export default App;
