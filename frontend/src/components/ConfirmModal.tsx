interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export const ConfirmModal = ({ isOpen, title, message, onConfirm, onCancel, isLoading }: ConfirmModalProps) => {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className="modal-title">{title}</div>
        <div className="modal-msg">{message}</div>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel} disabled={isLoading}>
            Annuler
          </button>
          <button className="btn-danger" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? 'Suppression…' : 'Confirmer'}
          </button>
        </div>
      </div>
    </div>
  );
};
