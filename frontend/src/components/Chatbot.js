import React, { useState, useRef, useEffect } from 'react';
import './Chatbot.css';

const Chatbot = ({ isOpen, onToggle, onLoanRequest }) => {
  const [messages, setMessages] = useState([
    {
      type: 'bot',
      content: 'Hello! I can help you apply for a loan. Please tell me about your loan needs including expected income. For example: "I need a loan for $500,000 for 36 months to start a solar panel business with expected income of $200,000."'
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const parseLoanRequestWithOllama = async (text) => {
    try {
      const prompt = `Parse the following loan request into a JSON object with these exact fields:
- amount: The loan amount as a number (remove $ and commas)
- duration: The loan duration in months as a number
- purpose: The business purpose as a string
- expected_income: The expected income/revenue as a number (remove $ and commas), default to 0 if not mentioned

Return ONLY valid JSON, no other text.

Loan request: "${text}"

Example output: {"amount": 500000, "duration": 36, "purpose": "solar panel business", "expected_income": 200000}`;

      const response = await fetch('http://127.0.0.1:11434/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'llama3.2',
          messages: [{ role: 'user', content: prompt }],
          stream: false,
          options: {
            temperature: 0.1,
            top_p: 0.1
          }
        })
      });

      if (!response.ok) {
        throw new Error(`Ollama API error: ${response.status}`);
      }

      const data = await response.json();
      const content = data.message?.content || '';

      // Try to parse the JSON response
      try {
        const parsed = JSON.parse(content.trim());
        return {
          amount: parsed.amount || null,
          duration: parsed.duration || null,
          purpose: parsed.purpose || null,
          expected_income: parsed.expected_income || 0
        };
      } catch (jsonError) {
        console.error('Failed to parse Ollama JSON response:', content);
        // Fallback to regex parsing if Ollama fails
        return parseLoanRequestFallback(text);
      }
    } catch (error) {
      console.error('Ollama parsing failed, using fallback:', error);
      // Fallback to regex parsing if Ollama is not available
      return parseLoanRequestFallback(text);
    }
  };

  const parseLoanRequestFallback = (text) => {
    // Input validation
    if (!text || typeof text !== 'string') {
      return { amount: null, duration: null, purpose: null, expected_income: 0 };
    }

    // Simple NLP parsing for loan details (fallback)
    const lowerText = text.toLowerCase();

    // Extract amount
    const amountMatch = text.match(/\$?(\d+(?:,\d{3})*(?:\.\d{2})?)/);
    const amount = amountMatch && amountMatch[1] ? parseFloat(amountMatch[1].replace(/,/g, '')) : null;

    // Extract duration
    const durationMatch = text.match(/(\d+)\s*(?:month|year)/i);
    const duration = durationMatch && durationMatch[1] ? parseInt(durationMatch[1]) : null;

    // Extract expected income
    const incomeMatch = text.match(/(?:income|revenue|earnings?|profit|expected)\s*(?:of|is|will be|about)?\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)/i);
    const expectedIncome = incomeMatch && incomeMatch[2] ? parseFloat(incomeMatch[2].replace(/,/g, '')) : null;

    // Extract purpose (everything after common phrases)
    let purpose = text || '';
    const removePhrases = [
      /i need a loan for/i,
      /i want to borrow/i,
      /loan for/i,
      /borrow/i,
      /\$?\d+(?:,\d{3})*(?:\.\d{2})?/i,
      /(\d+)\s*(?:month|year)/i,
      /(?:income|revenue|earnings?|profit|expected)\s*(?:of|is|will be|about)?\s*\$?\d+(?:,\d{3})*(?:\.\d{2})?/i
    ];

    try {
      removePhrases.forEach(phrase => {
        if (typeof purpose === 'string') {
          purpose = purpose.replace(phrase, '');
        }
      });

      if (typeof purpose === 'string') {
        purpose = purpose.trim().replace(/^to\s+/i, '').replace(/^for\s+/i, '');
      }

      if (!purpose) {
        // Try to extract from common patterns
        const purposePatterns = [
          /(?:for|to)\s+(.+)/i,
          /(?:start|open|build|buy|invest in)\s+(.+)/i
        ];

        for (const pattern of purposePatterns) {
          const match = text.match(pattern);
          if (match && match[1]) {
            purpose = match[1].trim();
            break;
          }
        }
      }
    } catch (error) {
      console.error('Error parsing purpose:', error);
      purpose = null;
    }

    return { amount, duration, purpose, expected_income: expectedIncome || 0 };
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    const userMessage = inputValue.trim();
    setMessages(prev => [...prev, { type: 'user', content: userMessage }]);
    setInputValue('');
    setIsTyping(true);

    try {
      const loanData = await parseLoanRequestWithOllama(userMessage);

      if (!loanData.amount || !loanData.duration || !loanData.purpose) {
        setMessages(prev => [...prev, {
          type: 'bot',
          content: 'I couldn\'t understand your loan request. Please provide the loan amount, duration, and purpose. For example: "I need $500,000 for 36 months to start a solar business."'
        }]);
        setIsTyping(false);
        return;
      }

      setMessages(prev => [...prev, {
        type: 'bot',
        content: `Processing your loan request for $${loanData.amount.toLocaleString()} over ${loanData.duration} months for "${loanData.purpose}". Please wait...`
      }]);

      await onLoanRequest(loanData);

      setMessages(prev => [...prev, {
        type: 'bot',
        content: 'Your loan request has been processed! Check the offers above.'
      }]);

    } catch (error) {
      console.error('Error processing loan:', error);
      setMessages(prev => [...prev, {
        type: 'bot',
        content: `Sorry, there was an error processing your request: ${error.message}. Please try again.`
      }]);
    }

    setIsTyping(false);
  };

  return (
    <>
      <div className={`chatbot-icon ${isOpen ? 'open' : ''}`} onClick={onToggle}>
        <span>💬</span>
      </div>

      {isOpen && (
        <div className="chatbot-container">
          <div className="chatbot-header">
            <h3>Loan Assistant</h3>
            <button className="close-btn" onClick={onToggle}>×</button>
          </div>

          <div className="chatbot-messages">
            {messages.map((message, index) => (
              <div key={index} className={`message ${message.type}`}>
                <div className="message-content">
                  {message.content}
                </div>
              </div>
            ))}
            {isTyping && (
              <div className="message bot typing">
                <div className="message-content">
                  <span className="typing-indicator">Typing...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form className="chatbot-input" onSubmit={handleSubmit}>
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Describe your loan needs..."
              disabled={isTyping}
            />
            <button type="submit" disabled={isTyping || !inputValue.trim()}>
              Send
            </button>
          </form>
        </div>
      )}
    </>
  );
};

export default Chatbot;
