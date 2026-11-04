import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Alert, Button, Stack, Text } from '@mantine/core';

interface Props {
  /** Name of the area shown in the fallback, e.g. "Diagnosi". */
  area: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Keeps a crash in one Doctor area (Diagnosi / Parametri / Laboratorio) from taking down the others. */
export class DoctorSectionErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Doctor ${this.props.area} error`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <Alert color="red" variant="light" data-testid="doctor-section-error">
          <Stack gap="xs">
            <Text size="sm">{`La sezione ${this.props.area} non è disponibile ora. Le altre sezioni restano utilizzabili.`}</Text>
            <Button size="xs" variant="light" color="red" w="fit-content" onClick={() => this.setState({ error: null })}>
              Riprova
            </Button>
          </Stack>
        </Alert>
      );
    }
    return this.props.children;
  }
}
