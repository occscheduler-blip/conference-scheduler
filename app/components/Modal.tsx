"use client";

import type { CSSProperties, ReactNode } from "react";

type ModalProps = {
  onClose: () => void;
  children: ReactNode;
  /** Override the default backdrop className (positioning, alignment, blur, etc.). */
  backdropClassName?: string;
  /** Inline style for the backdrop, useful for raising z-index above the default z-50. */
  backdropStyle?: CSSProperties;
};

const DEFAULT_BACKDROP =
  "fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4";

export function Modal({ onClose, children, backdropClassName, backdropStyle }: ModalProps) {
  return (
    <div
      className={backdropClassName ?? DEFAULT_BACKDROP}
      style={backdropStyle}
      onClick={onClose}
    >
      <div className="contents" onClick={(event) => event.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

export default Modal;
