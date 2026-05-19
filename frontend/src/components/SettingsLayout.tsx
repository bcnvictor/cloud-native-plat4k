import { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const NAV = [
  {
    label: 'Intégrations',
    items: [
      { path: '/credentials', icon: 'ti-cloud', label: 'Cloud & GitLab', dot: false },
    ],
  },
  {
    label: 'Workspace',
    items: [
      { path: '/apikeys', icon: 'ti-key', label: "Token d'accès", dot: false },
    ],
  },
];

interface Props {
  children: ReactNode;
  title: string;
  description?: string;
}

export const SettingsLayout = ({ children, title, description }: Props) => {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Paramètres</span>
      </div>
      <div className="settings-layout">
        <nav className="settings-nav">
          {NAV.map(group => (
            <div key={group.label}>
              <div className="settings-nav-label">{group.label}</div>
              {group.items.map(item => (
                <button
                  key={item.path}
                  className={`settings-nav-item${location.pathname === item.path ? ' active' : ''}`}
                  onClick={() => navigate(item.path)}
                >
                  <i className={`ti ${item.icon}`} aria-hidden="true" />
                  {item.label}
                  {item.dot && <span className="nav-status-dot green" />}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="settings-content">
          <div className="section-title-row">
            <div className="stitle">{title}</div>
            {description && <div className="sdesc">{description}</div>}
          </div>
          {children}
        </div>
      </div>
    </>
  );
};
