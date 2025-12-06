# Python Testing Patterns Skill

Expert knowledge of Python testing best practices and patterns.

## Testing Frameworks
- pytest: fixtures, parametrize, marks
- unittest: TestCase, setUp, tearDown
- hypothesis: property-based testing
- pytest-mock: mocking and patching

## Patterns

### Unit Testing
- Test one thing at a time
- Use descriptive test names
- AAA pattern (Arrange, Act, Assert)
- Test edge cases and error conditions

### Fixtures
```python
@pytest.fixture
def sample_data():
    return {"key": "value"}
```

### Parametrization
```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
])
def test_double(input, expected):
    assert double(input) == expected
```

### Mocking
```python
def test_with_mock(mocker):
    mock_api = mocker.patch('module.api_call')
    mock_api.return_value = {"data": "test"}
```

## Best Practices
- Test behavior, not implementation
- Keep tests independent
- Use fixtures for setup/teardown
- Mock external dependencies
- Aim for high coverage but test quality matters more

