"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  createTicket,
  fetchTicketCategories,
  fetchTicketDepartments,
  type Ticket,
  type TicketPriority,
  type TicketTaxonomyItem,
} from "@/lib/api";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useLocale } from "@/lib/i18n/LocaleProvider";
import styles from "./AgentsList.module.css";
import editModalStyles from "./EditRuleModal.module.css";

const PRIORITIES: TicketPriority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

/** Faz 62/63 — "Yeni Bilet Oluştur" modalı. Faz 63: `İlgili Cihaz`
 * alanı KALDIRILDI; Kategori (zorunlu) ve Departman (opsiyonel)
 * seçicileri backend'in `/api/tickets/categories` ⋅ `/departments`
 * uçlarından DİNAMİK beslenir (sabit liste yok). */
type Props = {
  onClose: () => void;
  onCreated: (ticket: Ticket) => void;
  // Faz 72 — vCenter VM Detay Modalı'ndan "Arıza/Talep Bileti Aç" ile
  // VM bilgisini ön-doldurmak için (başka bir çağrı noktası dokunulmaz,
  // ikisi de opsiyonel — varsayılan boş).
  initialTitle?: string;
  initialDescription?: string;
};

export function CreateTicketModal({ onClose, onCreated, initialTitle, initialDescription }: Props) {
  const { token } = useAuth();
  const { t } = useLocale();
  const k = t.tickets;

  const [title, setTitle] = useState(initialTitle ?? "");
  const [description, setDescription] = useState(initialDescription ?? "");
  const [priority, setPriority] = useState<TicketPriority>("MEDIUM");
  const [categories, setCategories] = useState<TicketTaxonomyItem[]>([]);
  const [departments, setDepartments] = useState<TicketTaxonomyItem[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([fetchTicketCategories(token), fetchTicketDepartments(token)])
      .then(([cats, deps]) => {
        setCategories(cats);
        setDepartments(deps);
        if (cats[0]) setCategoryId(cats[0].id);
      })
      .catch(() => {
        setCategories([]);
        setDepartments([]);
      });
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      const ticket = await createTicket(token, {
        title,
        description,
        category_id: categoryId,
        department_id: departmentId || null,
        priority,
      });
      onCreated(ticket);
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : k.createError);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={editModalStyles.overlay} role="presentation" onClick={onClose}>
      <form
        onSubmit={handleSubmit}
        role="dialog"
        aria-modal="true"
        aria-label={k.createTitle}
        className={editModalStyles.dialog}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className={editModalStyles.title}>{k.createTitle}</h3>

        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}
        {categories.length === 0 && <p className={styles.status}>{k.noCategories}</p>}

        <label className={styles.status}>
          {k.fieldTitle}
          <br />
          <input
            type="text"
            className={styles.searchInput}
            style={{ width: "100%" }}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </label>
        <label className={styles.status}>
          {k.fieldDescription}
          <br />
          <textarea
            className={styles.searchInput}
            style={{ width: "100%", minHeight: 90, resize: "vertical" }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <label className={styles.status}>
            {k.fieldCategory}
            <br />
            <select className={styles.searchInput} value={categoryId} onChange={(e) => setCategoryId(e.target.value)} required>
              <option value="" disabled>
                —
              </option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.status}>
            {k.fieldDepartment}
            <br />
            <select className={styles.searchInput} value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
              <option value="">{k.noDepartment}</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.status}>
            {k.fieldPriority}
            <br />
            <select className={styles.searchInput} value={priority} onChange={(e) => setPriority(e.target.value as TicketPriority)}>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {k[`priority${p}`]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={editModalStyles.actions}>
          <button type="button" className={styles.actionButton} onClick={onClose}>
            {k.cancel}
          </button>
          <button type="submit" className={styles.toolbarButton} disabled={saving || !categoryId}>
            {k.create}
          </button>
        </div>
      </form>
    </div>
  );
}
