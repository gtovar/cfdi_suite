import { act, type ReactElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';

export interface RenderedComponent {
  container: HTMLDivElement;
  rerender: (element: ReactElement) => void;
  unmount: () => void;
}

export function renderReact(element: ReactElement): RenderedComponent {
  const container = document.createElement('div');
  document.body.appendChild(container);

  const root = createRoot(container);

  const render = (nextElement: ReactElement) => {
    act(() => {
      root.render(nextElement);
    });
  };

  render(element);

  return {
    container,
    rerender: render,
    unmount: () => {
      cleanupRoot(root, container);
    },
  };
}

export function cleanupReact(container: HTMLDivElement) {
  container.remove();
}

function cleanupRoot(root: Root, container: HTMLDivElement) {
  act(() => {
    root.unmount();
  });
  cleanupReact(container);
}
