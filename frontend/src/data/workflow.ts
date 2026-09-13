// Server-only: the interactive-workflow features layered on top of the
// read-only gold.* facts - cash-call approvals, reconciliation case notes,
// HSE incident follow-ups, per-user alert thresholds, and support tickets.
// All write to the webapp's own Fabric SQL Database (see webapp-db.ts),
// keyed on the same natural keys gold.* uses, since gold.* itself can't be
// written to directly.

import { createServerFn } from "@tanstack/react-start";
import { connectWebappDb } from "@/data/webapp-db";

// ============================================================================
// Cash-call actions (approve / dispute / request clarification)
// ============================================================================

export type CashCallActionType = "approved" | "disputed" | "clarification_requested";

export type CashCallAction = {
  id: number;
  action: CashCallActionType;
  note: string | null;
  actedByEmail: string;
  actedByName: string | null;
  actedAt: string;
};

export const getCashCallActions = createServerFn({ method: "GET" })
  .validator((data: { periodId: string; fieldId: string; partnerId: string }) => data)
  .handler(async ({ data }): Promise<CashCallAction[]> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      const r = await pool
        .request()
        .input("p", sql.NVarChar, data.periodId)
        .input("f", sql.NVarChar, data.fieldId)
        .input("pt", sql.NVarChar, data.partnerId).query(`
          SELECT Id, Action, Note, ActedByEmail, ActedByName, ActedAt
          FROM dbo.CashCallActions
          WHERE PeriodId = @p AND FieldId = @f AND PartnerId = @pt
          ORDER BY ActedAt DESC
        `);
      return r.recordset.map((row) => ({
        id: row.Id,
        action: row.Action,
        note: row.Note,
        actedByEmail: row.ActedByEmail,
        actedByName: row.ActedByName,
        actedAt: new Date(row.ActedAt).toISOString(),
      }));
    } finally {
      await pool.close();
    }
  });

export const addCashCallAction = createServerFn({ method: "POST" })
  .validator(
    (data: {
      periodId: string;
      fieldId: string;
      partnerId: string;
      action: CashCallActionType;
      note: string | null;
      actedByEmail: string;
      actedByName: string | null;
    }) => data,
  )
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("p", sql.NVarChar, data.periodId)
        .input("f", sql.NVarChar, data.fieldId)
        .input("pt", sql.NVarChar, data.partnerId)
        .input("action", sql.NVarChar, data.action)
        .input("note", sql.NVarChar, data.note)
        .input("email", sql.NVarChar, data.actedByEmail)
        .input("name", sql.NVarChar, data.actedByName).query(`
          INSERT INTO dbo.CashCallActions (PeriodId, FieldId, PartnerId, Action, Note, ActedByEmail, ActedByName)
          VALUES (@p, @f, @pt, @action, @note, @email, @name)
        `);
    } finally {
      await pool.close();
    }
  });

// ============================================================================
// Reconciliation case notes (exception case management)
// ============================================================================

export type CaseNoteStatus = "open" | "resolved";

export type ReconciliationCaseNote = {
  id: number;
  note: string;
  assignedToEmail: string | null;
  status: CaseNoteStatus;
  createdByEmail: string;
  createdByName: string | null;
  createdAt: string;
};

export const getCaseNotes = createServerFn({ method: "GET" })
  .validator((data: { periodId: string; fieldId: string; partnerId: string }) => data)
  .handler(async ({ data }): Promise<ReconciliationCaseNote[]> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      const r = await pool
        .request()
        .input("p", sql.NVarChar, data.periodId)
        .input("f", sql.NVarChar, data.fieldId)
        .input("pt", sql.NVarChar, data.partnerId).query(`
          SELECT Id, Note, AssignedToEmail, Status, CreatedByEmail, CreatedByName, CreatedAt
          FROM dbo.ReconciliationCaseNotes
          WHERE PeriodId = @p AND FieldId = @f AND PartnerId = @pt
          ORDER BY CreatedAt DESC
        `);
      return r.recordset.map((row) => ({
        id: row.Id,
        note: row.Note,
        assignedToEmail: row.AssignedToEmail,
        status: row.Status,
        createdByEmail: row.CreatedByEmail,
        createdByName: row.CreatedByName,
        createdAt: new Date(row.CreatedAt).toISOString(),
      }));
    } finally {
      await pool.close();
    }
  });

export const addCaseNote = createServerFn({ method: "POST" })
  .validator(
    (data: {
      periodId: string;
      fieldId: string;
      partnerId: string;
      note: string;
      assignedToEmail: string | null;
      createdByEmail: string;
      createdByName: string | null;
    }) => data,
  )
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("p", sql.NVarChar, data.periodId)
        .input("f", sql.NVarChar, data.fieldId)
        .input("pt", sql.NVarChar, data.partnerId)
        .input("note", sql.NVarChar, data.note)
        .input("assignee", sql.NVarChar, data.assignedToEmail)
        .input("email", sql.NVarChar, data.createdByEmail)
        .input("name", sql.NVarChar, data.createdByName).query(`
          INSERT INTO dbo.ReconciliationCaseNotes (PeriodId, FieldId, PartnerId, Note, AssignedToEmail, CreatedByEmail, CreatedByName)
          VALUES (@p, @f, @pt, @note, @assignee, @email, @name)
        `);
    } finally {
      await pool.close();
    }
  });

export const resolveCaseNote = createServerFn({ method: "POST" })
  .validator((data: { id: number }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("id", sql.BigInt, data.id)
        .query(
          `UPDATE dbo.ReconciliationCaseNotes SET Status = 'resolved', UpdatedAt = SYSUTCDATETIME() WHERE Id = @id`,
        );
    } finally {
      await pool.close();
    }
  });

// ============================================================================
// HSE incident follow-up actions
// ============================================================================

export type IncidentActionStatus = "open" | "closed";

export type IncidentAction = {
  id: number;
  note: string;
  assignedToEmail: string | null;
  dueDate: string | null;
  status: IncidentActionStatus;
  createdByEmail: string;
  createdByName: string | null;
  createdAt: string;
};

export const getIncidentActions = createServerFn({ method: "GET" })
  .validator((data: { incidentId: string }) => data)
  .handler(async ({ data }): Promise<IncidentAction[]> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      const r = await pool.request().input("id", sql.NVarChar, data.incidentId).query(`
          SELECT Id, Note, AssignedToEmail, DueDate, Status, CreatedByEmail, CreatedByName, CreatedAt
          FROM dbo.IncidentActions
          WHERE IncidentId = @id
          ORDER BY CreatedAt DESC
        `);
      return r.recordset.map((row) => ({
        id: row.Id,
        note: row.Note,
        assignedToEmail: row.AssignedToEmail,
        dueDate: row.DueDate ? new Date(row.DueDate).toISOString().slice(0, 10) : null,
        status: row.Status,
        createdByEmail: row.CreatedByEmail,
        createdByName: row.CreatedByName,
        createdAt: new Date(row.CreatedAt).toISOString(),
      }));
    } finally {
      await pool.close();
    }
  });

export const addIncidentAction = createServerFn({ method: "POST" })
  .validator(
    (data: {
      incidentId: string;
      note: string;
      assignedToEmail: string | null;
      dueDate: string | null;
      createdByEmail: string;
      createdByName: string | null;
    }) => data,
  )
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("id", sql.NVarChar, data.incidentId)
        .input("note", sql.NVarChar, data.note)
        .input("assignee", sql.NVarChar, data.assignedToEmail)
        .input("due", sql.Date, data.dueDate)
        .input("email", sql.NVarChar, data.createdByEmail)
        .input("name", sql.NVarChar, data.createdByName).query(`
          INSERT INTO dbo.IncidentActions (IncidentId, Note, AssignedToEmail, DueDate, CreatedByEmail, CreatedByName)
          VALUES (@id, @note, @assignee, @due, @email, @name)
        `);
    } finally {
      await pool.close();
    }
  });

export const closeIncidentAction = createServerFn({ method: "POST" })
  .validator((data: { id: number }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("id", sql.BigInt, data.id)
        .query(`UPDATE dbo.IncidentActions SET Status = 'closed', UpdatedAt = SYSUTCDATETIME() WHERE Id = @id`);
    } finally {
      await pool.close();
    }
  });

// ============================================================================
// Per-user alert thresholds
// ============================================================================

export type ThresholdKey = "variance_watch_pct" | "variance_investigate_pct" | "downtime_alert_hours" | "uptime_alert_pct";

export const getUserThresholds = createServerFn({ method: "GET" })
  .validator((data: { email: string }) => data)
  .handler(async ({ data }): Promise<Record<string, number>> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      const r = await pool
        .request()
        .input("email", sql.NVarChar, data.email)
        .query(`SELECT MetricKey, ThresholdValue FROM dbo.UserThresholds WHERE Email = @email`);
      const out: Record<string, number> = {};
      for (const row of r.recordset) out[row.MetricKey] = Number(row.ThresholdValue);
      return out;
    } finally {
      await pool.close();
    }
  });

export const setUserThreshold = createServerFn({ method: "POST" })
  .validator((data: { email: string; metricKey: ThresholdKey; value: number }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("email", sql.NVarChar, data.email)
        .input("key", sql.NVarChar, data.metricKey)
        .input("value", sql.Decimal(9, 3), data.value).query(`
          MERGE dbo.UserThresholds AS target
          USING (SELECT @email AS Email, @key AS MetricKey) AS src
          ON target.Email = src.Email AND target.MetricKey = src.MetricKey
          WHEN MATCHED THEN UPDATE SET ThresholdValue = @value, UpdatedAt = SYSUTCDATETIME()
          WHEN NOT MATCHED THEN INSERT (Email, MetricKey, ThresholdValue) VALUES (@email, @key, @value);
        `);
    } finally {
      await pool.close();
    }
  });

// ============================================================================
// Support tickets
// ============================================================================

export type TicketCategory = "technical" | "finance" | "ops" | "hse";
export type TicketStatus = "open" | "in_progress" | "closed";

export type Ticket = {
  id: number;
  subject: string;
  description: string;
  category: TicketCategory;
  status: TicketStatus;
  createdByEmail: string;
  createdByName: string | null;
  createdAt: string;
  updatedAt: string;
};

export const listTickets = createServerFn({ method: "GET" }).handler(async (): Promise<Ticket[]> => {
  const pool = await connectWebappDb();
  try {
    const r = await pool.request().query(`
      SELECT Id, Subject, Description, Category, Status, CreatedByEmail, CreatedByName, CreatedAt, UpdatedAt
      FROM dbo.Tickets
      ORDER BY CreatedAt DESC
    `);
    return r.recordset.map((row) => ({
      id: row.Id,
      subject: row.Subject,
      description: row.Description,
      category: row.Category,
      status: row.Status,
      createdByEmail: row.CreatedByEmail,
      createdByName: row.CreatedByName,
      createdAt: new Date(row.CreatedAt).toISOString(),
      updatedAt: new Date(row.UpdatedAt).toISOString(),
    }));
  } finally {
    await pool.close();
  }
});

export const createTicket = createServerFn({ method: "POST" })
  .validator(
    (data: {
      subject: string;
      description: string;
      category: TicketCategory;
      createdByEmail: string;
      createdByName: string | null;
    }) => data,
  )
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("subject", sql.NVarChar, data.subject)
        .input("description", sql.NVarChar, data.description)
        .input("category", sql.NVarChar, data.category)
        .input("email", sql.NVarChar, data.createdByEmail)
        .input("name", sql.NVarChar, data.createdByName).query(`
          INSERT INTO dbo.Tickets (Subject, Description, Category, CreatedByEmail, CreatedByName)
          VALUES (@subject, @description, @category, @email, @name)
        `);
    } finally {
      await pool.close();
    }
  });

export const updateTicketStatus = createServerFn({ method: "POST" })
  .validator((data: { id: number; status: TicketStatus }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("id", sql.BigInt, data.id)
        .input("status", sql.NVarChar, data.status)
        .query(`UPDATE dbo.Tickets SET Status = @status, UpdatedAt = SYSUTCDATETIME() WHERE Id = @id`);
    } finally {
      await pool.close();
    }
  });

// ============================================================================
// Per-user, per-page dashboard widget layout (drag-to-reorder)
// ============================================================================

export const getDashboardLayout = createServerFn({ method: "GET" })
  .validator((data: { email: string; page: string }) => data)
  .handler(async ({ data }): Promise<string[] | null> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      const r = await pool
        .request()
        .input("email", sql.NVarChar, data.email)
        .input("page", sql.NVarChar, data.page)
        .query(`SELECT LayoutJson FROM dbo.UserDashboardLayout WHERE Email = @email AND Page = @page`);
      const row = r.recordset[0];
      if (!row) return null;
      try {
        const parsed = JSON.parse(row.LayoutJson);
        return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : null;
      } catch {
        return null;
      }
    } finally {
      await pool.close();
    }
  });

export const setDashboardLayout = createServerFn({ method: "POST" })
  .validator((data: { email: string; page: string; order: string[] }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("email", sql.NVarChar, data.email)
        .input("page", sql.NVarChar, data.page)
        .input("layout", sql.NVarChar, JSON.stringify(data.order)).query(`
          MERGE dbo.UserDashboardLayout AS target
          USING (SELECT @email AS Email, @page AS Page) AS src
          ON target.Email = src.Email AND target.Page = src.Page
          WHEN MATCHED THEN UPDATE SET LayoutJson = @layout, UpdatedAt = SYSUTCDATETIME()
          WHEN NOT MATCHED THEN INSERT (Email, Page, LayoutJson) VALUES (@email, @page, @layout);
        `);
    } finally {
      await pool.close();
    }
  });

export const resetDashboardLayout = createServerFn({ method: "POST" })
  .validator((data: { email: string; page: string }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("email", sql.NVarChar, data.email)
        .input("page", sql.NVarChar, data.page)
        .query(`DELETE FROM dbo.UserDashboardLayout WHERE Email = @email AND Page = @page`);
    } finally {
      await pool.close();
    }
  });

// ============================================================================
// Saved forecasts (what-if scenarios a user names and keeps)
// ============================================================================

export type SavedForecast = {
  id: number;
  name: string;
  periodId: string;
  uptimeAdjustment: number;
  forecastAdjustment: number;
  createdAt: string;
};

export const listSavedForecasts = createServerFn({ method: "GET" })
  .validator((data: { email: string }) => data)
  .handler(async ({ data }): Promise<SavedForecast[]> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      const r = await pool
        .request()
        .input("email", sql.NVarChar, data.email).query(`
          SELECT Id, Name, PeriodId, UptimeAdjustment, ForecastAdjustment, CreatedAt
          FROM dbo.SavedForecasts WHERE Email = @email ORDER BY CreatedAt DESC
        `);
      return r.recordset.map((row) => ({
        id: Number(row.Id),
        name: row.Name,
        periodId: row.PeriodId,
        uptimeAdjustment: Number(row.UptimeAdjustment),
        forecastAdjustment: Number(row.ForecastAdjustment),
        createdAt: new Date(row.CreatedAt).toISOString(),
      }));
    } finally {
      await pool.close();
    }
  });

export const saveForecast = createServerFn({ method: "POST" })
  .validator(
    (data: {
      email: string;
      name: string;
      periodId: string;
      uptimeAdjustment: number;
      forecastAdjustment: number;
    }) => data,
  )
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      await pool
        .request()
        .input("email", sql.NVarChar, data.email)
        .input("name", sql.NVarChar, data.name)
        .input("periodId", sql.NVarChar, data.periodId)
        .input("uptime", sql.Decimal(6, 2), data.uptimeAdjustment)
        .input("forecast", sql.Decimal(6, 2), data.forecastAdjustment).query(`
          INSERT INTO dbo.SavedForecasts (Email, Name, PeriodId, UptimeAdjustment, ForecastAdjustment)
          VALUES (@email, @name, @periodId, @uptime, @forecast)
        `);
    } finally {
      await pool.close();
    }
  });

export const deleteSavedForecast = createServerFn({ method: "POST" })
  .validator((data: { id: number; email: string }) => data)
  .handler(async ({ data }): Promise<void> => {
    const [{ default: sql }] = await Promise.all([import("mssql")]);
    const pool = await connectWebappDb();
    try {
      // Scoped to the owning email too, not just the id - a user should
      // only ever be able to delete their own saved forecasts.
      await pool
        .request()
        .input("id", sql.BigInt, data.id)
        .input("email", sql.NVarChar, data.email)
        .query(`DELETE FROM dbo.SavedForecasts WHERE Id = @id AND Email = @email`);
    } finally {
      await pool.close();
    }
  });
