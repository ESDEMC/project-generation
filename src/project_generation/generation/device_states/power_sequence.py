from project_generation.diagnostics import ProjectGenerationError
from project_generation.generation.models import GeneratedPowerDomain, GeneratedPowerSequenceStep


class PowerSequenceResolver:
    @classmethod
    def resolve(
        cls,
        *,
        state_name: str,
        power_domains: list[GeneratedPowerDomain],
        event: str,
        default_order: str,
    ) -> tuple[GeneratedPowerSequenceStep, ...]:
        by_name = {domain.name: domain for domain in power_domains}
        if len(by_name) != len(power_domains):
            duplicates = sorted(
                {domain.name for domain in power_domains if sum(item.name == domain.name for item in power_domains) > 1}
            )
            raise ProjectGenerationError(
                f'Device state "{state_name}" has duplicate power-domain names: {", ".join(duplicates)}'
            )

        dependencies: dict[str, str | None] = {}
        has_explicit_timing = False
        for domain in power_domains:
            timing = (domain.timing.get(event) or {}) if domain.timing else {}
            has_explicit_timing = has_explicit_timing or bool(timing)
            after = timing.get("after")
            if after is not None:
                after = str(after)
                if after not in by_name:
                    raise ProjectGenerationError(
                        f'Device state "{state_name}" power domain "{domain.name}" references unknown timing domain "{after}"'
                    )
                if after == domain.name:
                    raise ProjectGenerationError(
                        f'Device state "{state_name}" power domain "{domain.name}" cannot '
                        f'{event.replace("_", " ")} after itself'
                    )
            dependencies[domain.name] = after

        if default_order == "reverse_power_on" and not has_explicit_timing:
            power_on = cls.resolve(
                state_name=state_name,
                power_domains=power_domains,
                event="power_on",
                default_order="declaration",
            )
            ordered = [by_name[step.domain_name] for step in reversed(power_on)]
        else:
            ordered = cls._dependency_order(
                state_name=state_name,
                power_domains=power_domains,
                event=event,
                dependencies=dependencies,
            )

        return tuple(
            GeneratedPowerSequenceStep(
                index=index,
                domain_name=domain.name,
                assignment=domain.assignment,
                group_ids=domain.group_ids,
                group_names=domain.group_names,
                bias=dict(domain.bias),
                delay=float(((domain.timing.get(event) or {}) if domain.timing else {}).get("delay", 0.0)),
                after=dependencies[domain.name],
            )
            for index, domain in enumerate(ordered)
        )

    @staticmethod
    def _dependency_order(
        *,
        state_name: str,
        power_domains: list[GeneratedPowerDomain],
        event: str,
        dependencies: dict[str, str | None],
    ) -> list[GeneratedPowerDomain]:
        by_name = {domain.name: domain for domain in power_domains}
        ordered: list[GeneratedPowerDomain] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise ProjectGenerationError(
                    f'Device state "{state_name}" has a circular {event.replace("_", "-")} timing dependency '
                    f'involving "{name}"'
                )
            visiting.add(name)
            dependency = dependencies[name]
            if dependency is not None:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            ordered.append(by_name[name])

        for domain in power_domains:
            visit(domain.name)
        return ordered
