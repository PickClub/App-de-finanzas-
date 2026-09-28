import { createContext, useContext } from "react";

export const TabTransitionContext = createContext({
  navigate: (_name: string) => {},
  afterTransition: (callback: () => void): (() => void) => {
    callback();
    return () => {};
  },
});

export const useTabTransition = () => useContext(TabTransitionContext);
