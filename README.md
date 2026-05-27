# 🌱 Breathe ESG — Multi-Source Carbon Emissions Review Platform

Live Demo: https://breathe-esg-ten-theta.vercel.app/

Backend API: https://web-production-f66e0a.up.railway.app

Admin Panel:
https://web-production-f66e0a.up.railway.app/admin/

---

## Demo Credentials

This project is currently deployed as a prototype for evaluation/demo purposes.

### Analyst Login

Username:
analyst

Password:
breatheesg

⚠️ Authentication is temporarily hardcoded for prototype access only.

---

## About The Project

Breathe ESG is a full-stack ESG emissions management platform that helps organizations ingest, normalize, review, and audit carbon emissions data from multiple enterprise sources.

The system supports:

- SAP procurement emissions ingestion
- Utility emissions ingestion
- Travel emissions ingestion
- Analyst review workflows
- Emissions approval/rejection pipeline
- Suspicious emissions flagging
- Audit locking system
- ESG dashboard summaries
- Multi-tenant architecture

---

## Tech Stack

### Frontend
- React
- Vite
- TailwindCSS

### Backend
- Django
- Django REST Framework
- PostgreSQL

### Deployment
- Frontend → Vercel
- Backend → Railway
- Database → Railway PostgreSQL

---

## System Architecture

Frontend (Vercel)
↓
Django REST API (Railway)
↓
PostgreSQL Database (Railway)

---

## Features

### Emission Review Dashboard
- Review uploaded records
- Approve / reject emissions
- Track suspicious records
- Scope-based breakdowns

### File Ingestion
Supports:
- SAP CSV uploads
- Utility CSV uploads
- Travel CSV uploads

### Audit Controls
- Lock approved records
- Prevent further edits
- Maintain audit trail

---

## Prototype Notes

This deployment is a prototype and intentionally simplified for demonstration purposes.

Current prototype limitations:
- Hardcoded demo credentials
- Limited RBAC
- Simplified deployment setup
- No production-grade secrets management

---

## Local Setup

### Backend

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
