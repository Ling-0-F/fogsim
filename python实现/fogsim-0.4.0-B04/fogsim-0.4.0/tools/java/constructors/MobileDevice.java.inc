    /** Fixed-instance adapter only: no sampler, RNG, generator or implicit setup. */
    protected MobileDevice(int id, SystemState fixedState,
                           AbstractRule sequencingRule, AbstractRule routingRule) {
        this.id = id;
        this.systemState = fixedState;
        this.processingRate = 1.0; // unused placeholder: PT/UT/DT are supplied directly
        this.numTasksSampler = null;
        this.interReleaseTimeSampler = null;
        this.jobWeightSampler = null;
        this.workloadSampler = null;
        this.taskDataSampler = null;
        this.taskInputDataSampler = null;
        this.uploadBandwidthCloudSampler = null;
        this.downloadBandwidthCloudSampler = null;
        this.uploadBandwidthEdgeSampler = null;
        this.downloadBandwidthEdgeSampler = null;
        this.processingRateCloudSampler = null;
        this.processingRateEdgeSampler = null;
        this.workflowSampler = null;
        this.sequencingRule = sequencingRule;
        this.routingRule = routingRule;
        this.queue = new LinkedList<>();
        this.eventQueue = new PriorityQueue<>();
    }
