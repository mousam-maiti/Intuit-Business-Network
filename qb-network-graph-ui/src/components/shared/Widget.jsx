import { QB } from '@/constants/colors';

export function Widget({ title, action, children, className }) {
  return (
    <div className={'widget ' + (className || '')}>
      {title && (
        <div className="widget-header">
          <span className="widget-title">{title}</span>
          {action}
        </div>
      )}
      <div className="widget-body">{children}</div>
    </div>
  );
}
