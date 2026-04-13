# OptiSlot AO - Developer Guide

## "Antigravity" Architecture
This module implements the **Autonomous Operations (AO)** backend using a high-performance, async-first approach.

### Core Components

1.  **Thinking (Agents)**:
    *   `app/agents/vision.py`: Asynchronous simulation of video stream analysis.
    *   `app/agents/optimization.py`: Bin-packing logic interacting with SQLModel.
    *   `app/agents/sre.py`: Background health monitoring.

2.  **Memory (Hybrid DB)**:
    *   **Relational**: `ParkingSlot` (SQLModel) for ACID transaction state.
    *   **Vector**: `VectorStore` (Interface) for vehicle embeddings.

3.  **Reflexes (API)**:
    *   FastAPI with `BackgroundTasks` ensures the API acknowledges requests in **<10ms**.
    *   Heavy logic happens *after* the response is sent.

### Quick Start

1.  **Setup Environment**:
    ```bash
    cd OptiSlot_AO
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    ```

2.  **Run Dev Server**:
    ```bash
    uvicorn app.main:app --reload
    ```

3.  **Test Entry Event**:
    ```bash
    curl -X POST "http://127.0.0.1:8000/gate/GATE_01/entry"
    ```
    You should see an immediate `200 OK` and logs appearing in the console *after* the response.

### Docker Build
```bash
docker build -t optislot-ao:latest .
```
