"""A global attempt cursor called by the real dynamic admission/Arrival path."""
from dataclasses import asdict
from fogsim.errors import SimulationFailure


class ReplayWorkflowSource:
    def __init__(self, replay_input, *, purpose):
        self.archive = replay_input.archive
        self.capture = replay_input.capture
        self.purpose = purpose
        self.position = 0
        self.validated_count = 0
        self.last_call = None
        self.failure = None

    def _fail(self, code, message, **details):
        self.failure = dict(reason_code=code, message=message, **details)
        raise SimulationFailure(code, f'{code}: {message}; cursor={self.position}')

    def generate(self, cause, *, candidate_id):
        attempts = self.archive.generation_attempts
        self.last_call = dict(cause=asdict(cause), candidate_id=candidate_id,
                              requested_attempt_sequence=self.position + 1)
        if self.position == len(attempts):
            self._fail('REPLAY_INPUT_EXHAUSTED', 'additional input required; captured stream is finite',
                       actual=self.last_call)
        expected = attempts[self.position]
        record = self.archive.candidates[self.position]
        self.position += 1  # Exactly the next record; never search ahead or regroup.
        # Recorded event_sequence is diagnostic only, never a scheduling input.
        wanted = dict(phase=expected.cause.phase, owner_device_id=expected.cause.owner_device_id,
            clock_time=expected.cause.clock_time, causing_workflow_id=expected.cause.causing_workflow_id,
            candidate_id=record.workflow_input.candidate_id)
        actual = dict(phase=cause.phase, owner_device_id=cause.owner_device_id, clock_time=cause.clock_time,
            causing_workflow_id=cause.causing_workflow_id, candidate_id=candidate_id)
        if wanted != actual:
            self._fail('REPLAY_INPUT_DIVERGENCE', 'next attempt does not match generation call',
                       expected=wanted, actual=actual, record_id=record.record_id)
        return record.workflow_input

    def validate_admission(self, candidate, cause, reason):
        """Admission has independently computed release>clock before this check."""
        expected = self.archive.generation_attempts[self.position - 1]
        if (reason is None) != expected.observed_acceptance or reason != expected.rejection_reason:
            self._fail('REPLAY_INPUT_DIVERGENCE', 'observed acceptance differs from Python release gate',
                expected=dict(accepted=expected.observed_acceptance, reason=expected.rejection_reason),
                actual=dict(accepted=reason is None, reason=reason))
        self.validated_count += 1

    def summary(self):
        capture = self.capture
        available = len(self.archive.generation_attempts)
        return dict(kind='replay', purpose=self.purpose, new_experiment=self.purpose == 'reuse_inputs',
            available_attempt_count=available, consumed_record_count=self.position,
            validated_attempt_count=self.validated_count, remaining_attempt_count=available - self.position,
            input_capture_complete=capture.is_complete, last_call=self.last_call, failure=self.failure,
            coverage='finite_recorded_global_attempt_stream', rng_used=False)
