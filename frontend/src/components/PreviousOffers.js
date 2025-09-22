import React, { useState, useEffect } from 'react';
import './PreviousOffers.css';

const PreviousOffers = () => {
  const [allOffers, setAllOffers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOffers();
  }, []);

  const fetchOffers = async () => {
    try {
      const response = await fetch('http://localhost:8001/offers');
      if (response.ok) {
        const data = await response.json();
        setAllOffers(data.loan_requests || []);
      }
    } catch (error) {
      console.error('Error fetching offers:', error);
    }
    setLoading(false);
  };

  if (loading) {
    return <div className="previous-offers-loading">Loading previous offers...</div>;
  }

  if (!allOffers || allOffers.length === 0) {
    return (
      <div className="previous-offers-section">
        <h2>Previous Loan Offers</h2>
        <p className="no-offers">No previous offers available.</p>
      </div>
    );
  }

  return (
    <div className="previous-offers-section">
      <h2>Previous Loan Offers</h2>
      <div className="offers-timeline">
        {allOffers.map((request, requestIndex) => (
          <div key={requestIndex} className="loan-request-card">
            <div className="request-header">
              <h3>Loan Request #{allOffers.length - requestIndex}</h3>
              <span className="request-date">
                {new Date(request.timestamp).toLocaleDateString()}
              </span>
            </div>

            <div className="request-details">
              <p><strong>Amount:</strong> ${request.request.amount.toLocaleString()}</p>
              <p><strong>Duration:</strong> {request.request.duration} months</p>
              <p><strong>Purpose:</strong> {request.request.purpose}</p>
            </div>

            <div className="offers-summary">
              <h4>Bank Offers ({request.offers.length})</h4>
              <div className="offers-mini-grid">
                {request.offers.map((offerData, offerIndex) => {
                  const offer = offerData.offer || {};
                  const isRejected = offer.amount_approved === 0;

                  return (
                    <div key={offerIndex} className={`mini-offer-card ${isRejected ? 'rejected' : 'approved'}`}>
                      <div className="mini-header">
                        <span className="bank-name">{offerData.bank_name}</span>
                        <span className={`mini-status ${isRejected ? 'rejected' : 'approved'}`}>
                          {isRejected ? 'Rejected' : 'Approved'}
                        </span>
                      </div>

                      <div className="mini-details">
                        {isRejected ? (
                          <div className="mini-rejection">
                            <span>$0 approved</span>
                          </div>
                        ) : (
                          <>
                            <span>${offer.amount_approved?.toLocaleString() || 'N/A'}</span>
                            <span>{offer.interest_rate ? (offer.interest_rate * 100).toFixed(1) + '%' : 'N/A'}</span>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default PreviousOffers;
