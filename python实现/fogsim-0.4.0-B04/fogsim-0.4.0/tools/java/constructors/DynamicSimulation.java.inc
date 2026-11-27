    /** Fixed-instance adapter only: skip random provisioning and setup. */
    protected DynamicSimulation(SystemState fixedState) {
        this.systemState = fixedState;
        this.eventQueue = new PriorityQueue<>();
    }
