
import { useState } from 'react';
import {
  Table,
  Button,
  Drawer,
  Stack,
  Autocomplete,
  NumberInput,
  Text,
  Group,
  Title,
  Box,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Plus } from 'lucide-react';

interface AssetPosition {
  name: string;
  category: 'Equity' | 'Bond' | 'Gold' | 'Cash';
  quantity: number;
  loadPrice: number;
  currentPrice: number;
}

const mockData: AssetPosition[] = [
  {
    name: 'Vanguard FTSE All-World UCITS ETF',
    category: 'Equity',
    quantity: 100,
    loadPrice: 85.5,
    currentPrice: 92.3,
  },
  {
    name: 'iShares Core Corp Bond UCITS ETF',
    category: 'Bond',
    quantity: 200,
    loadPrice: 112.1,
    currentPrice: 115.8,
  },
  {
    name: 'iShares Core € Govt Bond UCITS ETF',
    category: 'Bond',
    quantity: 150,
    loadPrice: 130.4,
    currentPrice: 133.2,
  },
  { name: 'Xtrackers Physical Gold ETC', category: 'Gold', quantity: 50, loadPrice: 1800, currentPrice: 1950.5 },
  { name: 'Liquidità (Euro)', category: 'Cash', quantity: 10000, loadPrice: 1, currentPrice: 1 },
];

const assetOptions = [
  'Vanguard FTSE All-World UCITS ETF',
  'iShares Core Corp Bond UCITS ETF',
  'iShares Core € Govt Bond UCITS ETF',
  'Xtrackers Physical Gold ETC',
  'Liquidità (Euro)',
];

export function PortfolioPage() {
  const [opened, { open, close }] = useDisclosure(false);
  const [assets, setAssets] = useState<AssetPosition[]>(mockData);
  const [quantity, setQuantity] = useState<any | 0>(0);
  const [price, setPrice] = useState<any | 0>(0);
  const [assetName, setAssetName] = useState('');

  const totalValue = (typeof quantity === 'number' && typeof price === 'number') ? quantity * price : 0;

  const handleSave = () => {
    if (assetName && typeof quantity === 'number' && typeof price === 'number') {
        const newAsset: AssetPosition = {
            name: assetName,
            category: 'Equity', // Simplified for this example
            quantity: quantity,
            loadPrice: price,
            currentPrice: price, // Assuming current price is same as load price initially
        };
        setAssets([...assets, newAsset]);
        close();
        setAssetName('');
        setQuantity(0);
        setPrice(0);
    }
  };


  const rows = assets.map((asset) => {
    const totalValue = asset.quantity * asset.currentPrice;
    const pnl = (asset.currentPrice - asset.loadPrice) * asset.quantity;
    const pnlColor = pnl >= 0 ? 'green' : 'red';

    return (
      <Table.Tr key={asset.name}>
        <Table.Td>{asset.name}</Table.Td>
        <Table.Td>{asset.category}</Table.Td>
        <Table.Td>{asset.quantity}</Table.Td>
        <Table.Td>€{asset.loadPrice.toFixed(2)}</Table.Td>
        <Table.Td>€{asset.currentPrice.toFixed(2)}</Table.Td>
        <Table.Td>€{totalValue.toFixed(2)}</Table.Td>
        <Table.Td style={{ color: pnlColor }}>€{pnl.toFixed(2)}</Table.Td>
      </Table.Tr>
    );
  });

  return (
    <>
      <Group justify="space-between" mb="xl">
        <Title order={2}>Il Mio Portafoglio</Title>
        <Button onClick={open} leftSection={<Plus size={18} />}>
          Aggiungi Asset
        </Button>
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Nome/Ticker</Table.Th>
            <Table.Th>Categoria</Table.Th>
            <Table.Th>Quantità</Table.Th>
            <Table.Th>Prezzo di Carico</Table.Th>
            <Table.Th>Prezzo Attuale</Table.Th>
            <Table.Th>Valore Totale</Table.Th>
            <Table.Th>P&L</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>{rows}</Table.Tbody>
      </Table>

      <Drawer opened={opened} onClose={close} title="Nuova Transazione" position="right">
        <Stack>
          <Autocomplete
            label="Cerca Asset"
            placeholder="Seleziona o digita un asset"
            data={assetOptions}
            value={assetName}
            onChange={setAssetName}
            />
          <Group grow>
            <NumberInput label="Quantità" placeholder="Es. 10" value={quantity} onChange={setQuantity} min={0} />
            <NumberInput label="Prezzo Medio" placeholder="Es. 120.50" value={price} onChange={setPrice} min={0} decimalScale={2} />
          </Group>

          <Box>
            <Text>Controvalore Totale:</Text>
            <Text size="xl" fw={700}>
                €{totalValue.toFixed(2)}
            </Text>
          </Box>


          <Button onClick={handleSave} mt="md">
            Salva Transazione
          </Button>
        </Stack>
      </Drawer>
    </>
  );
}
