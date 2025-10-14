import { useState } from 'react';
import './App.css';

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'agent',
      text: 'Hello! How can I help you today?'
    }
  ]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [chatInput, setChatInput] = useState('');

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setSelectedFile(file);

    const newMessage = {
      id: messages.length + 2,
      sender: 'agent',
      text: `You've selected "${file.name}". What should I get from Keepa for these ASINs?`
    };

    setMessages(prevMessages => [...prevMessages, newMessage]);
  };

  const handleChatSubmit = (event) => {
    event.preventDefault();
    if (chatInput.trim() === '') return;

    const userMessage = {
      id: messages.length + 2,
      sender: 'user',
      text: chatInput
    };

    setMessages(prevMessages => [...prevMessages, userMessage]);
    setChatInput('');
    
    // Here we will eventually add logic to get a response from the agent
  };

  return (
    <div className="container">
      <header>
        <h1>E-commerce Analysis Agent</h1>
        <p>Your all-in-one tool for product research and analysis.</p>
      </header>
      
      <main className="layout-grid">
        
        <div className="main-column">
          <div className="card">
            <h2>Get Data by ASIN</h2>
            <p>Choose one of the methods below.</p>
            
            <div className="input-method">
              <h3>Option 1: Upload CSV File</h3>
              <p>The agent will ask for instructions in the chat.</p>
              <input 
                type="file" 
                id="csv-upload" 
                accept=".csv" 
                onChange={handleFileChange} 
              />
            </div>

            <div className="input-method">
              <h3>Option 2: Paste ASINs</h3>
              <textarea 
                id="asin-input"
                placeholder="Paste one ASIN per line..."
                rows="5"
              ></textarea>
              <button className="action-button">Get Info from ASINs</button>
            </div>
          </div>

          <div className="results-container">
              <h2>Results</h2>
              <p>Your results will appear here as a table.</p>
          </div>
        </div>

        <div className="sidebar-column">
          <div className="chat-container">
            <h2>Chat with Agent</h2>
            <div className="message-window">
              {messages.map(msg => (
                <div key={msg.id} className={`message ${msg.sender}-message`}>
                  <p>{msg.text}</p>
                </div>
              ))}
            </div>
            <form className="chat-input-form" onSubmit={handleChatSubmit}>
              <input 
                type="text" 
                placeholder="Type your message..." 
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
              />
              <button type="submit">Send</button>
            </form>
          </div>
        </div>

      </main>
    </div>
  );
}

export default App;
