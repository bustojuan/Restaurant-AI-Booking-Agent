import { en } from '../../i18n/en'
import { CameraOff, Utensils } from 'lucide-react'
import { useState } from 'react'
import type { Restaurant } from '../../types/bridge'
import { Pop } from '../ui/overlay'
import { Button } from '../ui/button'
export function RestaurantImage({
  restaurant,
  large = false,
}: {
  restaurant: Restaurant
  large?: boolean
}) {
  const [failed, setFailed] = useState(false)
  const asset = restaurant.images.find((i) => i.url === restaurant.primary_image_url)
  if (restaurant.has_photo && restaurant.primary_image_url && asset && !failed)
    return (
      <figure className={`restaurant-image ${large ? 'large' : ''}`}>
        <img
          src={restaurant.primary_image_url}
          draggable={false}
          alt={restaurant.name}
          onError={() => setFailed(true)}
        />
        <Pop
          className="photo-credit-popover"
          trigger={
            <button
              className="image-credit"
              aria-label={en.photoSourceAndLicense}
              title={`${asset.creator} · ${asset.license}`}
            >
              © {asset.creator}
            </button>
          }
        >
          <h3>{en.photoSource}</h3>
          <p>{asset.attribution}</p>
          <p>
            {asset.creator} · {asset.source}
          </p>
          <div>
            <Button onClick={() => void window.desktop?.openExternal(asset.source_page_url)}>
              {en.viewSource}
            </Button>
            <Button onClick={() => void window.desktop?.openExternal(asset.license_url)}>
              {asset.license}
            </Button>
          </div>
        </Pop>
      </figure>
    )
  return (
    <div
      className={`restaurant-image placeholder ${large ? 'large' : ''}`}
      title={en.photoUnavailable}
    >
      <Utensils size={large ? 32 : 21} />
      {large && (
        <span>
          <CameraOff size={12} /> {en.noPhoto}
        </span>
      )}
    </div>
  )
}
