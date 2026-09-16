import { Suspense } from "react";

import { LoginForm } from "@/components/LoginForm";
import styles from "../shared.module.css";

export default function LoginPage() {
  return (
    <main className={styles.page}>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
