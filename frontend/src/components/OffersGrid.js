import React, { useState } from 'react';
import './OffersGrid.css';

const OffersGrid = ({ offers, onOffersUpdate, onNotification }) => {
  const [negotiating, setNegotiating] = useState(null);

  const handleNegotiate = async (offerData, index) => {
    setNegotiating(index);
    try {
      const currentRate = offerData.offer.interest_rate;
      const targetRate = currentRate - 0.005;

      const response = await fetch('http://localhost:8001/negotiate_offer', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          bank_id: offerData.bank_id,
          current_offer: offerData.offer,
          target_rate: targetRate
        })
      });

      if (response.ok) {
        const result = await response.json();
        if (result.agreed) {
          const updatedOffers = [...offers];
          updatedOffers[index].offer = result.updated_offer;
          onOffersUpdate(updatedOffers);
          onNotification(`Negotiation successful! New interest rate: ${(result.new_rate * 100).toFixed(2)}%`, 'success');
        } else {
          onNotification(`Negotiation failed: ${result.reason}`, 'error');
        }
      } else {
        onNotification('Negotiation request failed', 'error');
      }
    } catch (error) {
      console.error('Negotiation error:', error);
      onNotification('Error during negotiation', 'error');
    }
    setNegotiating(null);
  };

  if (!offers || offers.length === 0) {
    return (
      <div className="offers-section">
        <h2>Bank Offers</h2>
        <p className="no-offers">No offers available yet. Use the chatbot to request a loan.</p>
      </div>
    );
  }

  return (
    <div className="offers-section">
      <h2>Bank Offers</h2>
      <div className="offers-grid">
        {offers.map((offerData, index) => {
          const offer = offerData.offer || {};
          const isRejected = offer.amount_approved === 0;

          return (
            <div key={index} className={`offer-card ${isRejected ? 'rejected' : ''}`}>
              <div className="offer-header">
                <h3 className='white'>{offerData.bank_name}</h3>
                <span className={`status ${isRejected ? 'rejected' : 'approved'}`}>
                  {isRejected ? 'Rejected' : 'Approved'}
                </span>
              </div>

              <div className="offer-details">
                {isRejected ? (
                  <div className="rejection-info">
                    <p><strong>Reason:</strong> {offer.esg_summary}</p>
                    <p className="amount-zero">$0 approved</p>
                  </div>
                ) : (
                  <>
                    <p><strong>Amount Approved:</strong> ${offer.amount_approved?.toLocaleString() || 'N/A'}</p>
                    <p><strong>Interest Rate:</strong> {offer.interest_rate ? (offer.interest_rate * 100).toFixed(2) + '%' : 'N/A'}</p>
                    <p><strong>Carbon Adjusted Rate:</strong> {offer.carbon_adjusted_rate ? (offer.carbon_adjusted_rate * 100).toFixed(2) + '%' : 'N/A'}</p>
                    <p><strong>Repayment Period:</strong> {offer.repayment_period || 'N/A'} months</p>
                    <p><strong>ESG Summary:</strong></p>
                    <p className="esg-summary">{offer.esg_summary || 'N/A'}</p>
                    <div className="offer-actions">
                      <button
                        className="negotiate-btn"
                        onClick={() => handleNegotiate(offerData, index)}
                        disabled={negotiating === index}
                      >
                        {negotiating === index ? 'Negotiating...' : 'Negotiate Rate'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default OffersGrid;
