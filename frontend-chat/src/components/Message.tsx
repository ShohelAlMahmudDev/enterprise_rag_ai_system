import { Bot, User } from 'lucide-react';

type MessageProps = {
  role: 'assistant' | 'user';
  content: string;
  subtle?: string;
};

export function Message({ role, content, subtle }: MessageProps) {
  return (
    <div className={`message ${role}`}>
      <div className={`avatar ${role}`}>
        {role === 'assistant' ? <Bot size={18} /> : <User size={18} />}
      </div>
      <div className="message-body">
        <div className="message-meta">{role === 'assistant' ? 'Assistant' : 'You'}</div>
        <div className="message-content">{content}</div>
        {subtle ? <div className="message-subtle">{subtle}</div> : null}
      </div>
    </div>
  );
}
