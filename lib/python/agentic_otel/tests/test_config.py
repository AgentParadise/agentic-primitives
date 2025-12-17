"""Tests for OTelConfig."""

from agentic_otel.config import OTelConfig


class TestOTelConfig:
    """Tests for OTelConfig dataclass."""

    def test_minimal_config(self) -> None:
        """Test creating config with only required fields."""
        config = OTelConfig(endpoint="http://collector:4317")

        assert config.endpoint == "http://collector:4317"
        assert config.service_name == "agentic-agent"
        assert config.protocol == "grpc"

    def test_custom_service_name(self) -> None:
        """Test setting custom service name."""
        config = OTelConfig(
            endpoint="http://collector:4317",
            service_name="my-custom-agent",
        )

        assert config.service_name == "my-custom-agent"

    def test_http_protocol(self) -> None:
        """Test using HTTP protocol."""
        config = OTelConfig(
            endpoint="http://collector:4318",
            protocol="http/protobuf",
        )

        env = config.to_env()
        assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"

    def test_resource_attributes(self) -> None:
        """Test adding custom resource attributes."""
        config = OTelConfig(
            endpoint="http://collector:4317",
            resource_attributes={
                "deployment.environment": "production",
                "service.version": "1.0.0",
            },
        )

        env = config.to_env()
        attrs = env["OTEL_RESOURCE_ATTRIBUTES"]
        assert "deployment.environment=production" in attrs
        assert "service.version=1.0.0" in attrs


class TestOTelConfigToEnv:
    """Tests for to_env() method."""

    def test_basic_env_vars(self) -> None:
        """Test basic environment variable generation."""
        config = OTelConfig(endpoint="http://localhost:4317")
        env = config.to_env()

        assert env["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
        assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4317"
        assert env["OTEL_EXPORTER_OTLP_PROTOCOL"] == "grpc"
        assert env["OTEL_METRICS_EXPORTER"] == "otlp"
        assert env["OTEL_LOGS_EXPORTER"] == "otlp"
        assert env["OTEL_TRACES_EXPORTER"] == "otlp"
        assert env["OTEL_SERVICE_NAME"] == "agentic-agent"

    def test_cardinality_control_default(self) -> None:
        """Test that cardinality control is enabled by default."""
        config = OTelConfig(endpoint="http://localhost:4317")
        env = config.to_env()

        # By default, tool and model names are included
        assert "CLAUDE_CODE_OTEL_TOOL_NAME_ENABLED" not in env
        assert "CLAUDE_CODE_OTEL_MODEL_NAME_ENABLED" not in env

    def test_cardinality_control_disabled(self) -> None:
        """Test disabling cardinality dimensions."""
        config = OTelConfig(
            endpoint="http://localhost:4317",
            include_tool_name=False,
            include_model_name=False,
        )
        env = config.to_env()

        assert env["CLAUDE_CODE_OTEL_TOOL_NAME_ENABLED"] == "false"
        assert env["CLAUDE_CODE_OTEL_MODEL_NAME_ENABLED"] == "false"

    def test_no_resource_attributes(self) -> None:
        """Test that OTEL_RESOURCE_ATTRIBUTES is omitted when empty."""
        config = OTelConfig(endpoint="http://localhost:4317")
        env = config.to_env()

        assert "OTEL_RESOURCE_ATTRIBUTES" not in env

    def test_resource_attributes_format(self) -> None:
        """Test resource attributes are formatted correctly."""
        config = OTelConfig(
            endpoint="http://localhost:4317",
            resource_attributes={
                "aef.workflow.execution_id": "exec-123",
                "aef.workflow.phase_id": "phase-impl",
            },
        )
        env = config.to_env()

        attrs = env["OTEL_RESOURCE_ATTRIBUTES"]
        # Should be comma-separated key=value pairs
        assert "aef.workflow.execution_id=exec-123" in attrs
        assert "aef.workflow.phase_id=phase-impl" in attrs
        assert "," in attrs


class TestOTelConfigSDKAttributes:
    """Tests for to_sdk_resource_attributes() method."""

    def test_includes_service_name(self) -> None:
        """Test that service name is included."""
        config = OTelConfig(
            endpoint="http://localhost:4317",
            service_name="test-agent",
        )
        attrs = config.to_sdk_resource_attributes()

        assert attrs["service.name"] == "test-agent"

    def test_includes_custom_attributes(self) -> None:
        """Test that custom attributes are included."""
        config = OTelConfig(
            endpoint="http://localhost:4317",
            resource_attributes={
                "custom.attr": "value",
            },
        )
        attrs = config.to_sdk_resource_attributes()

        assert attrs["custom.attr"] == "value"

    def test_merges_service_and_custom(self) -> None:
        """Test that service name and custom attrs are merged."""
        config = OTelConfig(
            endpoint="http://localhost:4317",
            service_name="my-agent",
            resource_attributes={
                "env": "prod",
            },
        )
        attrs = config.to_sdk_resource_attributes()

        assert attrs["service.name"] == "my-agent"
        assert attrs["env"] == "prod"
