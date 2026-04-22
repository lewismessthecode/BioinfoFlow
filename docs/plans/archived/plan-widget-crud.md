# Plan: Widget CRUD Feature

Add full CRUD support for widgets — a reusable component registry for bioinformatics dashboard panels.

## Phase 1: Database Schema

- Add `Widget` model to `backend/app/models/widget.py` with fields: id, name, description, widget_type, config (JSON), created_at, updated_at
- Add `widgets` table via Alembic migration
- Add `WidgetRepository` in `backend/app/repositories/widget.py`
- Acceptance: migration applies cleanly, model can be imported, repository CRUD methods work

## Phase 2: API Endpoints

- Add Pydantic schemas in `backend/app/schemas/widget.py` (WidgetCreate, WidgetUpdate, WidgetResponse)
- Add CRUD routes in `backend/app/api/v1/widgets.py` (GET list, GET detail, POST create, PUT update, DELETE)
- Register router in `backend/app/api/v1/__init__.py`
- Add service layer in `backend/app/services/widget_service.py`
- Depends on: Phase 1
- Acceptance: API tests pass, schema validation works, standard envelope responses

## Phase 3: Frontend Components

- Add `WidgetList` component in `frontend/components/widgets/widget-list.tsx`
- Add `WidgetForm` component in `frontend/components/widgets/widget-form.tsx`
- Add API hooks in `frontend/lib/hooks/use-widgets.ts`
- Add widgets page at `frontend/app/(app)/widgets/page.tsx`
- Add sidebar link for widgets
- Depends on: Phase 2
- Acceptance: component tests pass, list renders widgets, form creates/edits widgets
