## Developing a Verifier Plugin
### 1 Role & Responsibilities
A Verifier Plugin evaluates whether an executed action achieved its intended effect.
It operates after action execution, using observable signals (e.g., screenshots, state changes) to assess success.

In ZhiXing, a verifier is responsible for:

Checking post-action outcomes

Providing structured success / failure signals

Supplying feedback for retries or correction

Remaining independent from planning and execution logic

### 2 Verifier Design Pattern
Verifier plugins follow a post-execution validation pattern:
```bash
Action Executed
        ↓
Observable Evidence (screenshots, state)
        ↓
Verifier.verify(...)
        ↓
VerifierResult (success / failure / retry)
```
They act as a guardrail between execution and subsequent planning steps.

### 3 Example
File location
```bash
docs/plugins/verifier/example_verifier.py
```
Example Implementation
```python
@register_verifier("example_verifier")
class ExampleVerifier(BaseVerifier):
    """
    Example Verifier
    Always marks TAP actions as successful.
    """

    def verify(self, input_data: VerifierInput) -> VerifierResult:
        action = input_data.action

        if action.type == ActionType.TAP:
            return VerifierResult(
                is_success=True,
                feedback="Tap action assumed successful"
            )

        return VerifierResult(
            is_success=True,
            feedback="Action skipped verification"
        )
```

