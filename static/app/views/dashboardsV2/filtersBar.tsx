import {Fragment} from 'react';
import styled from '@emotion/styled';
import {Location} from 'history';

import Feature from 'sentry/components/acl/feature';
import Button from 'sentry/components/button';
import ButtonBar from 'sentry/components/buttonBar';
import DatePageFilter from 'sentry/components/datePageFilter';
import EnvironmentPageFilter from 'sentry/components/environmentPageFilter';
import FeatureBadge from 'sentry/components/featureBadge';
import PageFilterBar from 'sentry/components/organizations/pageFilterBar';
import ProjectPageFilter from 'sentry/components/projectPageFilter';
import {t} from 'sentry/locale';
import space from 'sentry/styles/space';
import {ReleasesProvider} from 'sentry/utils/releases/releasesProvider';
import useOrganization from 'sentry/utils/useOrganization';
import usePageFilters from 'sentry/utils/usePageFilters';

import ReleasesSelectControl from './releasesSelectControl';
import {DashboardFilters} from './types';

type FiltersBarProps = {
  filters: DashboardFilters;
  hasUnsavedChanges: boolean;
  isEditingDashboard: boolean;
  isPreview: boolean;
  location: Location;
  onCancel: () => void;
  onDashboardFilterChange: (activeFilters: DashboardFilters) => void;
  onSave: () => void;
};

function getReleaseParams(release: string | string[]) {
  if (Array.isArray(release)) {
    return release;
  }

  return [release];
}

export default function FiltersBar({
  filters,
  hasUnsavedChanges,
  isEditingDashboard,
  isPreview,
  location,
  onCancel,
  onDashboardFilterChange,
  onSave,
}: FiltersBarProps) {
  const {selection} = usePageFilters();
  const organization = useOrganization();

  const selectedReleases =
    (location.query?.release
      ? getReleaseParams(location.query.release)
      : filters?.release) ?? [];

  return (
    <Wrapper>
      <PageFilterBar condensed>
        <ProjectPageFilter disabled={isEditingDashboard} />
        <EnvironmentPageFilter disabled={isEditingDashboard} />
        <DatePageFilter alignDropdown="left" disabled={isEditingDashboard} />
      </PageFilterBar>
      <Feature features={['dashboards-top-level-filter']}>
        <Fragment>
          <FilterButtons>
            <FilterButton>
              <ReleasesProvider organization={organization} selection={selection}>
                <ReleasesSelectControl
                  handleChangeFilter={onDashboardFilterChange}
                  selectedReleases={selectedReleases}
                  isDisabled={isEditingDashboard}
                />
              </ReleasesProvider>
            </FilterButton>
          </FilterButtons>
          {hasUnsavedChanges && !isEditingDashboard && !isPreview && (
            <FilterButtons>
              <Button priority="primary" onClick={onSave}>
                {t('Save')}
              </Button>
              <Button onClick={onCancel}>{t('Cancel')}</Button>
            </FilterButtons>
          )}
          <FeatureBadge type="beta" />
        </Fragment>
      </Feature>
    </Wrapper>
  );
}

const Wrapper = styled('div')`
  display: flex;
  flex-direction: row;
  gap: ${space(1.5)};
  margin-bottom: ${space(2)};

  @media (max-width: ${p => p.theme.breakpoints.small}) {
    display: grid;
    grid-auto-flow: row;
  }
`;

const FilterButtons = styled(ButtonBar)`
  display: grid;
  gap: ${space(1.5)};

  @media (min-width: ${p => p.theme.breakpoints.small}) {
    display: flex;
    align-items: flex-start;
    gap: ${space(1.5)};
  }
`;

const FilterButton = styled('div')`
  @media (min-width: ${p => p.theme.breakpoints.small}) {
    max-width: 300px;
  }
`;
