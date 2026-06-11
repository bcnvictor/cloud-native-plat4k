import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '@/components/StatusBadge';

describe('StatusBadge', () => {
  it('affiche "Running" pour le statut running', () => {
    render(<StatusBadge status="running" />);
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('affiche "En cours…" pour le statut pending', () => {
    render(<StatusBadge status="pending" />);
    expect(screen.getByText('En cours…')).toBeInTheDocument();
  });

  it('affiche "Arrêtée" pour le statut stopped', () => {
    render(<StatusBadge status="stopped" />);
    expect(screen.getByText('Arrêtée')).toBeInTheDocument();
  });

  it('affiche "Terminée" pour le statut terminated', () => {
    render(<StatusBadge status="terminated" />);
    expect(screen.getByText('Terminée')).toBeInTheDocument();
  });

  it('affiche "Échec" pour le statut error', () => {
    render(<StatusBadge status="error" />);
    expect(screen.getByText('Échec')).toBeInTheDocument();
  });

  it('applique la classe CSS du statut sur le dot', () => {
    const { container } = render(<StatusBadge status="running" />);
    expect(container.querySelector('.status-dot.running')).toBeInTheDocument();
  });

  it('applique la classe CSS du statut sur le texte', () => {
    const { container } = render(<StatusBadge status="error" />);
    expect(container.querySelector('.status-text.error')).toBeInTheDocument();
  });
});
