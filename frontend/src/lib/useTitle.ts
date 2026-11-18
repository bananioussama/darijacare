import { useEffect } from "react";

/** Titre de l'onglet : « Page · DarijaCare ». */
export function useTitle(page: string): void {
  useEffect(() => {
    document.title = `${page} · DarijaCare`;
  }, [page]);
}
